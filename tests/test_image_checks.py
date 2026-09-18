"""Offline image checks using fake Harbor environments."""
import asyncio
import inspect
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import TaskConfig
from harbor.models.trial.config import EnvironmentConfig
from px_eval import image_checks as checks


FACTORY_SIGNATURE = inspect.signature(EnvironmentFactory.create_environment)


class ImageCheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.enterContext(chdir(self.root))
        self.task = self.root / "task"
        (self.task / "environment").mkdir(parents=True)
        (self.task / "environment/Dockerfile").write_text("FROM scratch\n")
        (self.task / "preflight").mkdir()
        self.script = self.task / "preflight/preflight_checks.sh"
        self.script.write_text("exit 0\n")
        self.config = TaskConfig.model_validate({
            "environment": {"docker_image": "example/agent@sha256:" + "a" * 64,
                            "cpus": 2, "memory_mb": 4096, "storage_mb": 8192,
                            "network_mode": "no-network"},
            "agent": {"timeout_sec": 123, "user": "agent", "network_mode": "allowlist",
                      "allowed_hosts": ["example.com"]},
            "verifier": {"network_mode": "no-network", "environment": {
                "docker_image": "example/verifier@sha256:" + "b" * 64,
                "cpus": 4, "memory_mb": 8192, "storage_mb": 16384,
                "network_mode": "allowlist", "allowed_hosts": ["baseline.example"]}},
        })
        self.save_config()
        self.runtime = EnvironmentConfig(type="modal")
        self.logs = self.root / "logs"

    def save_config(self):
        (self.task / "task.toml").write_text(self.config.model_dump_toml())

    def environment(self):
        env = AsyncMock(spec=BaseEnvironment)
        env.exec.return_value = ExecResult(return_code=0, stdout="ok", stderr="")
        return env

    def factory(self, made):
        def create(*args, **kwargs):
            env = self.environment()
            made.append((FACTORY_SIGNATURE.bind(*args, **kwargs).arguments, env))
            return env
        return patch.object(checks.EnvironmentFactory, "create_environment", side_effect=create)

    async def check(self, role="agent", **kwargs):
        kwargs.setdefault("environment", self.runtime)
        kwargs.setdefault("logs_dir", self.logs)
        return await checks.check_image(self.task, role, **kwargs)

    async def test_agent_image_boots_like_a_trial(self):
        made = []
        runtime = EnvironmentConfig(type="modal", extra_allowed_hosts=["example.com", "api.example"],
                                    kwargs={"registry_secret": "pull", "sandbox_timeout_secs": 900}, env={"X": "1"})
        with self.factory(made):
            result = await self.check(environment=runtime, timeout_sec=75)
        [(bound, env)] = made
        self.assertIs(result, env.exec.return_value)
        self.assertEqual(bound["type"].value, "modal")
        self.assertEqual(bound["environment_dir"], self.task / "environment")
        self.assertEqual(bound["environment_name"], "task")
        self.assertLess(len(bound["session_id"]), 64)
        self.assertEqual(bound["task_env_config"], self.config.environment)
        self.assertEqual(bound["trial_paths"].agent_dir, self.logs / "agent")
        self.assertTrue((self.logs / "agent").is_dir())
        options = bound["kwargs"]
        # Caller hosts merge into the agent's baseline as Harbor does for rollouts.
        self.assertEqual(options["network_policy"].network_mode.value, "allowlist")
        self.assertEqual(options["network_policy"].allowed_hosts, ["example.com", "api.example"])
        # The caller's native settings reach the backend untouched.
        self.assertEqual(options["registry_secret"], "pull")
        self.assertEqual(options["sandbox_timeout_secs"], 900)
        self.assertEqual(options["persistent_env"], {"X": "1"})
        env.start.assert_awaited_once_with(force_build=False)
        env.ensure_dirs.assert_awaited_once_with(["/logs/agent", "/logs/verifier"])
        env.run_healthcheck.assert_awaited_once_with()
        env.upload_file.assert_awaited_once_with(self.script, "/tmp/preflight_checks.sh")
        env.exec.assert_awaited_once_with(
            "bash /tmp/preflight_checks.sh", user="agent",
            env={"PX_TASK_NETWORK_MODE": "allowlist", "PX_IMAGE_ROLE": "agent"}, timeout_sec=75)
        env.download_dir.assert_awaited_once_with("/logs/agent", self.logs / "agent")
        env.stop.assert_awaited_once_with(delete=True)

    async def test_verifier_image_uses_its_own_config_and_skips_healthcheck(self):
        made = []
        with self.factory(made):
            await self.check("verifier", environment=EnvironmentConfig(type="modal", extra_allowed_hosts=["api.example"]))
        [(bound, env)] = made
        self.assertEqual(bound["task_env_config"], self.config.verifier.environment)
        self.assertEqual(bound["environment_dir"], self.task / "tests")
        self.assertEqual(bound["kwargs"]["network_policy"].allowed_hosts, ["baseline.example"])
        env.run_healthcheck.assert_not_awaited()
        self.assertEqual(env.exec.await_args.kwargs["user"], "agent")
        self.assertEqual(env.exec.await_args.kwargs["env"],
                         {"PX_TASK_NETWORK_MODE": "allowlist", "PX_IMAGE_ROLE": "verifier"})
        self.assertEqual(env.exec.await_args.kwargs["timeout_sec"], 1800)

    async def test_missing_task_or_verifier_image_fails_before_any_sandbox(self):
        self.config.verifier.environment = None
        self.save_config()
        with patch.object(checks.EnvironmentFactory, "create_environment") as create:
            with self.assertRaises(ValueError):
                await self.check("verifier")
            with self.assertRaises(FileNotFoundError):
                await checks.check_image(self.root / "missing", "agent",
                                         environment=self.runtime, logs_dir=self.logs)
            create.assert_not_called()

    async def test_errors_propagate_and_the_sandbox_still_stops(self):
        for phase, error in (("start", RuntimeError("start failed")), ("start", asyncio.CancelledError()),
                             ("exec", RuntimeError("exec failed")), ("exec", asyncio.TimeoutError()),
                             ("exec", asyncio.CancelledError())):
            with self.subTest(phase=phase, error=type(error).__name__):
                env = self.environment()
                getattr(env, phase).side_effect = error
                with patch.object(checks.EnvironmentFactory, "create_environment", return_value=env):
                    with self.assertRaises(type(error)):
                        await self.check()
                env.stop.assert_awaited_once_with(delete=True)
                # Whatever the script wrote before failing is still downloaded.
                self.assertEqual(env.download_dir.await_count, 1 if phase == "exec" else 0)

    async def test_script_path_is_relative_to_the_task(self):
        env = self.environment()
        with patch.object(checks.EnvironmentFactory, "create_environment", return_value=env):
            await self.check(script=Path("checks/other.sh"))
        env.upload_file.assert_awaited_once_with(self.task / "checks/other.sh", checks.SANDBOX_SCRIPT)

    async def test_stop_follows_the_environment_delete_setting(self):
        env = self.environment()
        with patch.object(checks.EnvironmentFactory, "create_environment", return_value=env):
            await self.check(environment=EnvironmentConfig(type="modal", delete=False))
        env.stop.assert_awaited_once_with(delete=False)

    async def test_caller_environment_is_not_modified(self):
        runtime = EnvironmentConfig(type="modal", kwargs={"registry_secret": "s"}, extra_allowed_hosts=["h"])
        before = runtime.model_copy(deep=True)
        with patch.object(checks.EnvironmentFactory, "create_environment", return_value=self.environment()):
            await self.check(environment=runtime)
        self.assertEqual(runtime, before)


if __name__ == "__main__":
    unittest.main()
