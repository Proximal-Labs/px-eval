import asyncio
from pathlib import Path
from typing import Literal
from uuid import uuid4

from harbor.environments.base import ExecResult
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import TaskConfig
from harbor.models.task.paths import TaskPaths
from harbor.models.trial.config import EnvironmentConfig
from harbor.models.trial.paths import EnvironmentPaths, TrialPaths
from harbor.trial.network_policy import resolve_agent_env_baseline, resolve_verifier_env_baseline

ImageRole = Literal["agent", "verifier"]
SANDBOX_SCRIPT = "/tmp/preflight_checks.sh"


async def check_image(
    task_path: Path, role: ImageRole, *, environment: EnvironmentConfig, logs_dir: Path,
    script: Path = Path("preflight/preflight_checks.sh"), timeout_sec: int = 1800,
) -> ExecResult:
    """Start the task's image for `role`, run `script` (relative to the task), stop it."""
    task = TaskPaths(task_path)
    config = TaskConfig.model_validate_toml(task.config_path.read_text())
    if role == "agent":
        image, build_dir = config.environment, task.environment_dir
        baseline = resolve_agent_env_baseline(config, environment)
    else:
        image, build_dir = config.verifier.environment, task.tests_dir
        if image is None:
            raise ValueError(f"{task.task_dir.name} has no separate verifier image")
        baseline = resolve_verifier_env_baseline(config, environment, None, env_config=image)
    paths = TrialPaths(logs_dir)
    paths.mkdir()
    env = EnvironmentFactory.create_environment_from_config(
        config=environment, environment_dir=build_dir, environment_name=task.task_dir.name,
        session_id=f"check-{uuid4().hex}", trial_paths=paths, task_env_config=image,
        network_policy=baseline,
    )
    try:
        await asyncio.wait_for(env.start(force_build=False), timeout=config.environment.build_timeout_sec)
        # A trial mounts these and Harbor makes them writable; this environment has no mounts.
        await env.ensure_dirs([EnvironmentPaths.agent_dir.as_posix(), EnvironmentPaths.verifier_dir.as_posix()])
        if role == "agent":
            await env.run_healthcheck()
        await env.upload_file(task.task_dir / script, SANDBOX_SCRIPT)
        try:
            return await env.exec(
                f"bash {SANDBOX_SCRIPT}", user=config.agent.user,
                env={"PX_TASK_NETWORK_MODE": baseline.network_mode.value, "PX_IMAGE_ROLE": role},
                timeout_sec=timeout_sec,
            )
        finally:
            await env.download_dir(EnvironmentPaths.agent_dir.as_posix(), paths.agent_dir)
    finally:
        await env.stop(delete=environment.delete)
