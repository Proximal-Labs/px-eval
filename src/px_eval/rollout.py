from collections.abc import Sequence
from pathlib import Path
from typing import Any

from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.job.result import JobResult
from harbor.models.task.config import TaskConfig as TaskSpec
from harbor.models.task.verifier_mode import task_has_any_shared_verifier
from harbor.models.trial.config import (
    AgentConfig,
    EnvironmentConfig,
    TaskConfig,
    VerifierConfig,
)


def require_separate_verifier(task_paths: Sequence[Path]) -> None:
    """Raise if a task would grade in the agent's sandbox instead of a verifier sandbox of its own."""
    shared = [
        path.name for path in task_paths
        if task_has_any_shared_verifier(TaskSpec.model_validate_toml((path / "task.toml").read_text()))
    ]
    if shared:
        raise ValueError(f"tasks without a separate verifier environment: {', '.join(shared)}")


def build_rollout_config(
    task_paths: Sequence[Path],
    *,
    agent: str,
    model: str,
    environment: EnvironmentConfig,
    n_attempts: int = 1,
    n_concurrent_trials: int = 1,
    verify: bool = True,
    agent_kwargs: dict[str, Any] | None = None,
    agent_env: dict[str, str] | None = None,
) -> JobConfig:
    """Build a Harbor job for local tasks and one agent/model.

    With `verify`, each trial grades right after its agent, in the task's own verifier sandbox.
    `agent_kwargs` and `agent_env` are Harbor's `AgentConfig.kwargs` and `AgentConfig.env`
    (`--ak` and `--ae` of `harbor run`); `env` values may be `${VAR}` templates.
    """
    if not model.strip():
        raise ValueError("model must be non-empty")
    if verify:
        require_separate_verifier(task_paths)
    return JobConfig(
        tasks=[TaskConfig(path=path) for path in task_paths],
        agents=[AgentConfig(name=agent, model_name=model, kwargs=dict(agent_kwargs or {}),
                            env=dict(agent_env or {}))],
        environment=environment.model_copy(deep=True),
        verifier=VerifierConfig(disable=not verify),
        n_attempts=n_attempts,
        n_concurrent_trials=n_concurrent_trials,
    )


async def run_rollouts(config: JobConfig) -> JobResult:
    """Run a fresh job; Harbor persists config, logs, artifacts and results."""
    config = config.model_copy(deep=True)
    config.jobs_dir = config.jobs_dir.resolve()
    (config.jobs_dir / config.job_name).mkdir(parents=True, exist_ok=False)
    job = await Job.create(config)
    return await job.run()
