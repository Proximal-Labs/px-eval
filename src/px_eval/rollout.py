from collections.abc import Sequence
from pathlib import Path

from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.job.result import JobResult
from harbor.models.trial.config import (
    AgentConfig,
    EnvironmentConfig,
    TaskConfig,
    VerifierConfig,
)


def build_rollout_config(
    task_paths: Sequence[Path],
    *,
    agent: str,
    model: str,
    environment: EnvironmentConfig,
    n_attempts: int = 1,
    n_concurrent_trials: int = 1,
    verify: bool = True,
) -> JobConfig:
    """Build a Harbor job for local tasks and one agent/model."""
    if not model.strip():
        raise ValueError("model must be non-empty")
    return JobConfig(
        tasks=[TaskConfig(path=path) for path in task_paths],
        agents=[AgentConfig(name=agent, model_name=model)],
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
