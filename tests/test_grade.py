import asyncio
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from harbor.models.trial.config import EnvironmentConfig

from px_eval import build_grade_config, build_rollout_config, run_grades


class GradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(chdir(self.root))
        self.task = self.root / "task"
        self.source = self.root / "jobs" / "rollout-job"
        self.source.mkdir(parents=True)

    def config(self, **kwargs):
        kwargs.setdefault("environment", EnvironmentConfig(type="modal"))
        return build_grade_config(self.source, [self.task], **kwargs)

    def test_regrades_the_recorded_job_with_verification_on(self):
        config = self.config()
        self.assertTrue(config.is_regrade)
        self.assertEqual(len(config.source_jobs), 1)
        source = config.source_jobs[0]
        self.assertEqual((source.action, source.type), ("regrade", "local"))
        self.assertEqual(source.path, self.source.resolve())
        self.assertEqual([task.path for task in config.tasks], [self.task])
        self.assertFalse(config.verifier.disable)
        self.assertEqual(config.n_concurrent_trials, 1)
        self.assertEqual(type(config).model_validate_json(config.model_dump_json()), config)

    def test_environment_is_copied(self):
        runtime = EnvironmentConfig(type="modal", env={"A": "1"})
        config = self.config(environment=runtime, n_concurrent_trials=4)
        config.environment.env["A"] = "2"
        self.assertEqual(runtime.env, {"A": "1"})
        self.assertEqual(config.n_concurrent_trials, 4)

    def test_invalid_inputs(self):
        env = EnvironmentConfig(type="modal")
        with self.assertRaises(ValueError):
            build_grade_config(self.root / "missing", [self.task], environment=env)
        with self.assertRaises(ValueError):
            build_grade_config(self.source, [], environment=env)

    def test_run_grades_runs_a_fresh_job_and_returns_harbor_result(self):
        config = self.config()
        result = object()
        job = AsyncMock()
        job.run.return_value = result
        with patch("px_eval.rollout.Job.create", new_callable=AsyncMock, return_value=job) as create:
            self.assertIs(asyncio.run(run_grades(config)), result)
            passed = create.await_args.args[0]
            self.assertTrue(passed.is_regrade)
            self.assertTrue((config.jobs_dir / config.job_name).is_dir())

    def test_run_grades_rejects_a_rollout_config(self):
        rollout = build_rollout_config([self.task], agent="codex", model="m",
                                       environment=EnvironmentConfig(type="modal"))
        with patch("px_eval.rollout.Job.create", new_callable=AsyncMock) as create:
            with self.assertRaises(ValueError):
                asyncio.run(run_grades(rollout))
            create.assert_not_awaited()


class AgentOptionTests(unittest.TestCase):
    def test_agent_kwargs_and_custom_import_path(self):
        config = build_rollout_config(
            [Path("task")], agent="my_pkg.agents:Custom", model="m",
            environment=EnvironmentConfig(type="modal"), agent_kwargs={"max_turns": 5},
        )
        agent = config.agents[0]
        self.assertEqual(agent.name, "my_pkg.agents:Custom")
        self.assertEqual(agent.kwargs, {"max_turns": 5})

    def test_agent_kwargs_are_copied_and_default_empty(self):
        kwargs = {"a": 1}
        config = build_rollout_config([Path("task")], agent="codex", model="m",
                                      environment=EnvironmentConfig(type="modal"), agent_kwargs=kwargs)
        config.agents[0].kwargs["a"] = 2
        self.assertEqual(kwargs, {"a": 1})
        plain = build_rollout_config([Path("task")], agent="codex", model="m",
                                     environment=EnvironmentConfig(type="modal"))
        self.assertEqual(plain.agents[0].kwargs, {})


if __name__ == "__main__":
    unittest.main()
