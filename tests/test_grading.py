"""Offline checks that Harbor turns a grading config into regrade trials."""
import asyncio
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from harbor.job import Job
from harbor.models.task.id import LocalTaskId
from harbor.models.trial.config import EnvironmentConfig, TaskConfig, TrialConfig
from harbor.models.trial.result import AgentInfo, TrialResult

from px_eval import build_grading_config, build_rollout_config, require_separate_verifier, run_grading

SEPARATE = '[environment]\ndocker_image = "example/agent"\n\n[verifier.environment]\ndocker_image = "example/verifier"\n'
SHARED = '[environment]\ndocker_image = "example/agent"\n'


def make_task(root: Path, name: str, toml: str = SEPARATE) -> Path:
    (root / name).mkdir(parents=True)
    (root / name / "task.toml").write_text(toml)
    return root / name


def make_trial(job_dir: Path, task: Path) -> None:
    """A finished trial as Harbor records it: config, result and artifacts manifest."""
    trial_dir = job_dir / f"{task.name}__abc"
    (trial_dir / "artifacts").mkdir(parents=True)
    (trial_dir / "artifacts/manifest.json").write_text("[]")
    result = TrialResult(
        task_name=task.name, trial_name=trial_dir.name, trial_uri=trial_dir.as_uri(),
        task_id=LocalTaskId(path=task), task_checksum="0",
        config=TrialConfig(task=TaskConfig(path=task)), agent_info=AgentInfo(name="codex", version="1"),
    )
    (trial_dir / "result.json").write_text(result.model_dump_json())
    (trial_dir / "config.json").write_text(result.config.model_dump_json())


class GradingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.enterContext(chdir(self.root))
        self.task = make_task(self.root / "tasks", "task")
        self.source = self.root / "jobs/source"
        make_trial(self.source, self.task)
        self.runtime = EnvironmentConfig(type="modal", kwargs={"registry_secret": "pull"})

    def test_config_regrades_the_source_job(self):
        config = build_grading_config(self.source, [self.task], environment=self.runtime, n_concurrent_trials=3)
        [source] = config.source_jobs
        self.assertEqual((source.action, source.type, source.path), ("regrade", "local", self.source))
        self.assertEqual([task.path for task in config.tasks], [self.task])
        self.assertFalse(config.verifier.disable)
        self.assertEqual(config.n_concurrent_trials, 3)
        self.assertEqual(config.environment, self.runtime)
        self.assertIsNot(config.environment, self.runtime)
        self.assertEqual(type(config).model_validate_json(config.model_dump_json()), config)

    def test_harbor_builds_one_regrade_trial_per_finished_trial(self):
        config = build_grading_config(self.source, [self.task], environment=self.runtime)
        job = asyncio.run(Job.create(config))
        self.assertEqual(len(job), 1)

    def test_harbor_rejects_a_source_trial_without_its_task(self):
        make_trial(self.source, make_task(self.root / "tasks", "other"))
        config = build_grading_config(self.source, [self.task], environment=self.runtime)
        with self.assertRaisesRegex(ValueError, "other"):
            asyncio.run(Job.create(config))

    def test_run_grading_runs_a_fresh_harbor_job(self):
        config = build_grading_config(self.source, [self.task], environment=self.runtime)
        job = AsyncMock()
        job.run.return_value = result = object()
        with patch("px_eval.rollout.Job.create", new_callable=AsyncMock, return_value=job) as create:
            self.assertIs(asyncio.run(run_grading(config)), result)
        self.assertEqual(create.await_args.args[0].source_jobs, config.source_jobs)
        self.assertTrue((config.jobs_dir / config.job_name).is_dir())

    def test_run_grading_rejects_a_rollout_config(self):
        rollout = build_rollout_config([self.task], agent="codex", model="m", environment=self.runtime)
        with patch("px_eval.rollout.Job.create", new_callable=AsyncMock) as create:
            with self.assertRaisesRegex(ValueError, "build_grading_config"):
                asyncio.run(run_grading(rollout))
        create.assert_not_awaited()

    def test_shared_verifier_is_rejected(self):
        shared = make_task(self.root / "tasks", "shared", SHARED)
        with self.assertRaisesRegex(ValueError, "shared"):
            require_separate_verifier([self.task, shared])
        with self.assertRaisesRegex(ValueError, "shared"):
            build_grading_config(self.source, [shared], environment=self.runtime)
        explicit = make_task(self.root / "tasks", "explicit", SHARED + '\n[verifier]\nenvironment_mode = "separate"\n')
        require_separate_verifier([self.task, explicit])


if __name__ == "__main__":
    unittest.main()
