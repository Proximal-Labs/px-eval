"""Per-task runtime configuration for frontier-swe-v2: the caller's config plus the task's job.yaml."""

from functools import cache
from pathlib import Path

from harbor.cli.config_sources import load_config_source
from harbor.models.task.config import TaskConfig
from harbor.models.trial.config import EnvironmentConfig


PROXIMUS = "harbor_proximus:Proximus"


def task_environment(task: Path, base: EnvironmentConfig, budget: float | None = None) -> EnvironmentConfig:
    """Apply the task's `job.yaml` environment profile onto `base`.

    Scalar fields from the profile win; `kwargs` and `env` merge with the profile winning.
    TASK_BUDGET_SECS is `budget`, or else the task's agent budget from task.toml; the sandbox
    timer reads it.
    """
    profile: dict = {}
    if (task / "job.yaml").is_file():
        profile = load_config_source(task / "job.yaml").get("environment") or {}
    if budget is None:
        budget = TaskConfig.model_validate_toml((task / "task.toml").read_text()).agent.timeout_sec
    timer = {"TASK_BUDGET_SECS": str(int(budget))} if budget is not None else {}
    return EnvironmentConfig.model_validate({
        **base.model_dump(),
        **profile,
        "kwargs": {**base.kwargs, **profile.get("kwargs", {})},
        "env": {**base.env, **timer, **profile.get("env", {})},
    })


@cache
def is_proximus(agent: str) -> bool:
    """True when `agent` is a `module:Class` path to Proximus or a subclass of it."""
    if ":" not in agent:
        return False
    try:
        from harbor.agents.factory import AgentFactory
        from harbor.models.trial.config import AgentConfig
        from harbor_proximus import Proximus

        agent_class = AgentFactory.get_agent_class_from_config(AgentConfig(name=agent))
    except (ImportError, AttributeError, ValueError):
        return False
    return isinstance(agent_class, type) and issubclass(agent_class, Proximus)


def task_agent(task: Path, agent: str, model: str, overrides: dict) -> tuple[dict, float | None]:
    """Agent kwargs and hard agent timeout for one task and model.

    For Proximus, the kwargs come from the task's `[agent.proximus]` table, with `overrides`
    on top and `task_provides_timer` defaulting to whether the task ships sandbox-timer, and the
    hard timeout leaves room above the work budget for the exit submit and restore.
    Other agents get `overrides` and the task's own timeout.
    """
    if not is_proximus(agent):
        return overrides, None
    from harbor_proximus import hard_timeout_sec, task_agent_kwargs

    # frontier-swe-v2 instructions describe the in-image sandbox-timer, so the
    # system prompt must not add a second clock.
    defaults = {"task_provides_timer": (task / "environment" / "sandbox_timer.sh").is_file()}
    kwargs = task_agent_kwargs(task, model, overrides, defaults=defaults)
    return kwargs, hard_timeout_sec(kwargs)
