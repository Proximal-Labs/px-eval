import asyncio
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from harbor.models.trial.config import EnvironmentConfig

from px_eval import build_rollout_config, run_rollouts
from test_grading import SHARED, make_task


class RolloutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(chdir(self.root))  # run_rollouts writes under jobs/ in the cwd
        self.task = make_task(self.root, "task")

    def config(self, **kwargs):
        kwargs.setdefault("environment", EnvironmentConfig(type="modal"))
        return build_rollout_config(
            [self.task], agent="codex", model="test-model",
            **kwargs,
        )

    def test_defaults_and_native_config_roundtrip(self):
        config = self.config()
        self.assertEqual(config.tasks[0].path, self.task)
        self.assertEqual(config.agents[0].name, "codex")
        self.assertEqual(config.agents[0].model_name, "test-model")
        self.assertIsNone(config.agents[0].import_path)
        self.assertEqual(config.environment.type.value, "modal")
        self.assertTrue(config.environment.delete)
        self.assertFalse(config.verifier.disable)
        self.assertEqual(config.n_attempts, 1)
        self.assertEqual(config.n_concurrent_trials, 1)
        self.assertEqual(config.retry.max_retries, 0)
        self.assertEqual(type(config).model_validate_json(config.model_dump_json()), config)
        self.assertEqual(config.jobs_dir, Path("jobs"))
        self.assertFalse(config.jobs_dir.exists())
        self.assertNotIn("job_name", config.model_fields_set)

    def test_options(self):
        config = self.config(environment=EnvironmentConfig(type="docker"), verify=False, n_attempts=2,
                             n_concurrent_trials=3)
        self.assertTrue(config.verifier.disable)
        self.assertEqual(config.environment.type.value, "docker")
        self.assertEqual(config.n_attempts, 2)
        self.assertEqual(config.n_concurrent_trials, 3)

    def test_environment_is_copied_so_the_caller_object_stays_unchanged(self):
        runtime = EnvironmentConfig(
            type="modal", kwargs={"registry_secret": "caller-secret", "modal_vm_runtime": True},
            extra_allowed_hosts=["api.example"], env={"TASK_BUDGET_SECS": "456"},
        )
        config = self.config(environment=runtime)
        self.assertEqual(config.environment, runtime)
        config.environment.kwargs["registry_secret"] = "changed"
        config.environment.extra_allowed_hosts.append("other.example")
        config.environment.env["TASK_BUDGET_SECS"] = "789"
        self.assertEqual(runtime.kwargs["registry_secret"], "caller-secret")
        self.assertEqual(runtime.extra_allowed_hosts, ["api.example"])
        self.assertEqual(runtime.env, {"TASK_BUDGET_SECS": "456"})
        self.assertEqual(self.config().environment.env, {})
        self.assertEqual(self.config().environment.extra_allowed_hosts, [])

    def test_invalid_inputs(self):
        base = dict(task_paths=[self.task], agent="codex", model="test",
                    environment=EnvironmentConfig(type="modal"))
        for override in [
            {"model": " "},
            {"n_attempts": 0},
            {"n_concurrent_trials": 0},
        ]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                build_rollout_config(**(base | override))

    def test_multiple_tasks(self):
        other = make_task(self.root, "other")
        config = build_rollout_config([self.task, other], agent="codex", model="test",
                                      environment=EnvironmentConfig(type="modal"))
        self.assertEqual([task.path for task in config.tasks], [self.task, other])

    def test_grading_now_needs_a_separate_verifier(self):
        shared = make_task(self.root, "shared", SHARED)
        with self.assertRaisesRegex(ValueError, "shared"):
            build_rollout_config([self.task, shared], agent="codex", model="test",
                                 environment=EnvironmentConfig(type="modal"))
        config = build_rollout_config([shared], agent="codex", model="test",
                                      environment=EnvironmentConfig(type="modal"), verify=False)
        self.assertTrue(config.verifier.disable)

    def test_execution_returns_harbor_result_without_interpreting_it(self):
        config = self.config()
        result = object()  # Returned unchanged, including when Harbor records trial errors.
        job = AsyncMock()
        job.run.return_value = result
        with patch("px_eval.rollout.Job.create", new_callable=AsyncMock, return_value=job) as create:
            self.assertIs(asyncio.run(run_rollouts(config)), result)
            passed = create.await_args.args[0]
            self.assertEqual(passed, config.model_copy(
                update={"jobs_dir": config.jobs_dir.resolve()}))
            self.assertIsNot(passed, config)
            job.run.assert_awaited_once_with()
            self.assertTrue((config.jobs_dir / config.job_name).is_dir())
            with self.assertRaises(FileExistsError):
                asyncio.run(run_rollouts(config))
            create.assert_awaited_once()

    def test_errors_and_cancellation_propagate(self):
        for index, error in enumerate([RuntimeError("launch failed"), asyncio.CancelledError()]):
            with self.subTest(error=type(error).__name__):
                config = self.config()
                config.job_name = f"error-{index}"
                job = AsyncMock()
                job.run.side_effect = error
                with patch("px_eval.rollout.Job.create", new_callable=AsyncMock, return_value=job):
                    with self.assertRaises(type(error)):
                        asyncio.run(run_rollouts(config))
        with patch("px_eval.rollout.Job.create", new_callable=AsyncMock, side_effect=RuntimeError("setup")):
            with self.assertRaisesRegex(RuntimeError, "setup"):
                asyncio.run(run_rollouts(self.config()))


if __name__ == "__main__":
    unittest.main()
