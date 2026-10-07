from collections.abc import Sequence
from pathlib import Path

from harbor.models.job.config import JobConfig, SourceJobConfig
from harbor.models.job.result import JobResult
from harbor.models.trial.config import EnvironmentConfig, TaskConfig

from px_eval.rollout import run_job


def build_grade_config(
    source_job_dir: Path,
    task_paths: Sequence[Path],
    *,
    environment: EnvironmentConfig,
    n_concurrent_trials: int = 1,
) -> JobConfig:
    """Build a Harbor job that re-runs only the verifiers on a recorded job.

    Each recorded trial in `source_job_dir` is graded against the task with the
    same name in `task_paths`, in a fresh verifier environment. The agent is not
    re-run and the source job is never modified. Tasks must use separate-mode
    verifiers that read their inputs from the recorded artifacts.
    """
    source_job_dir = Path(source_job_dir)
    if not source_job_dir.is_dir():
        raise ValueError(f"source job directory does not exist: {source_job_dir}")
    if not task_paths:
        raise ValueError("task_paths must name at least one task")
    return JobConfig(
        tasks=[TaskConfig(path=path) for path in task_paths],
        source_jobs=[SourceJobConfig(action="regrade", type="local", path=source_job_dir.resolve())],
        environment=environment.model_copy(deep=True),
        n_concurrent_trials=n_concurrent_trials,
    )


async def run_grades(config: JobConfig) -> JobResult:
    """Run a fresh grading job built by `build_grade_config`."""
    if not config.is_regrade:
        raise ValueError("config has no source job; use build_grade_config")
    return await run_job(config)
