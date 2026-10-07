from collections.abc import Sequence
from pathlib import Path

from harbor.models.job.config import JobConfig, SourceJobConfig
from harbor.models.job.result import JobResult
from harbor.models.trial.config import EnvironmentConfig, TaskConfig

from px_eval.rollout import require_separate_verifier, run_rollouts


def build_grading_config(
    job_dir: Path,
    task_paths: Sequence[Path],
    *,
    environment: EnvironmentConfig,
    n_concurrent_trials: int = 1,
) -> JobConfig:
    """Build a Harbor job that grades the finished trials of `job_dir` in fresh verifier sandboxes.

    `task_paths` must include each task of the source job. The source job stays unchanged.
    """
    require_separate_verifier(task_paths)
    return JobConfig(
        tasks=[TaskConfig(path=path) for path in task_paths],
        environment=environment.model_copy(deep=True),
        source_jobs=[SourceJobConfig(action="regrade", type="local", path=job_dir.resolve())],
        n_concurrent_trials=n_concurrent_trials,
    )


async def run_grading(config: JobConfig) -> JobResult:
    """Run a grading job from `build_grading_config` as a new Harbor job."""
    if not config.is_regrade:
        raise ValueError("this config has no source job; use build_grading_config")
    return await run_rollouts(config)
