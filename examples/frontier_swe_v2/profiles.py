"""Per-task runtime configuration for frontier-swe-v2: the caller's config plus the task's job.yaml."""

from pathlib import Path

from harbor.cli.config_sources import load_config_source
from harbor.models.task.config import TaskConfig
from harbor.models.trial.config import EnvironmentConfig


def task_environment(task: Path, base: EnvironmentConfig) -> EnvironmentConfig:
    """Apply the task's `job.yaml` environment profile onto `base`.

    Scalar fields from the profile win; `kwargs` and `env` merge with the profile winning.
    TASK_BUDGET_SECS is the task's agent budget from task.toml; the sandbox timer reads it.
    """
    profile: dict = {}
    if (task / "job.yaml").is_file():
        profile = load_config_source(task / "job.yaml").get("environment") or {}
    budget = TaskConfig.model_validate_toml((task / "task.toml").read_text()).agent.timeout_sec
    timer = {"TASK_BUDGET_SECS": str(int(budget))} if budget is not None else {}
    return EnvironmentConfig.model_validate({
        **base.model_dump(),
        **profile,
        "kwargs": {**base.kwargs, **profile.get("kwargs", {})},
        "env": {**base.env, **timer, **profile.get("env", {})},
    })
