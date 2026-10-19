"""Run frontier-swe-v2 tasks with one agent and one or more models.

Tasks that share a runtime profile (your configuration plus the task's job.yaml) and an agent
configuration run in one Harbor job per model, under jobs/ in the current directory.
"""

import argparse
import asyncio
import json
from pathlib import Path

from harbor.agents.factory import AgentFactory
from harbor.cli.config_sources import load_config_source
from harbor.cli.utils import parse_env_vars, parse_kwargs
from harbor.models.trial.config import EnvironmentConfig

from px_eval import build_rollout_config, run_rollouts
from profiles import PROXIMUS, is_proximus, task_agent, task_environment

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("tasks_root", type=Path, help="The tasks/ directory of a frontier-swe-v2 checkout")
parser.add_argument("--environment", type=Path, required=True, help="Native EnvironmentConfig in YAML or JSON")
parser.add_argument("--agent", required=True,
                    help="Harbor agent name, module:Class for a custom agent, or proximus")
parser.add_argument("--ak", "--agent-kwarg", dest="agent_kwarg", action="append", metavar="KEY=VALUE",
                    help="Agent option, as in harbor run. Repeatable. For proximus, these go on top "
                         "of the task's [agent.proximus] table")
parser.add_argument("--ae", "--agent-env", dest="agent_env", action="append", metavar="KEY=VALUE",
                    help="Agent environment variable, as in harbor run, e.g. a provider key. Repeatable")
parser.add_argument("--model", action="append", required=True, metavar="PROVIDER/MODEL",
                    help="Model for the agent; repeat for several models")
parser.add_argument("--task", action="append", metavar="NAME", help="Run only this task; repeatable")
parser.add_argument("--attempts", type=int, default=1, help="Rollouts per task and model")
parser.add_argument("--concurrent", type=int, default=1, help="Trials to run at the same time")
parser.add_argument("--grade", choices=["now", "later"], default="now",
                    help="Grade each rollout right after its agent, or later with grade.py")
parser.add_argument("--agent-timeout", type=int, metavar="SECONDS",
                    help="Cap the agent phase; useful for smoke runs. Not for proximus: set "
                         "--ak time_budget_sec instead, so it can finish before the cap")
parser.add_argument("--verifier-timeout", type=int, metavar="SECONDS",
                    help="Ceiling for the verifier phase; shorter task timeouts stay")
args = parser.parse_args()

tasks: list[Path] = sorted(path.parent for path in args.tasks_root.glob("*/task.toml"))
if args.task:
    tasks = [task for task in tasks if task.name in args.task]
if not tasks:
    parser.error(f"no task directories with task.toml under {args.tasks_root}")
try:
    agent_kwargs = parse_kwargs(args.agent_kwarg)
    agent_env = parse_env_vars(args.agent_env)
except ValueError as e:
    parser.error(str(e))
environment = EnvironmentConfig.model_validate(load_config_source(args.environment), extra="forbid")
agent = PROXIMUS if args.agent == "proximus" else args.agent
proximus = is_proximus(agent)
if proximus and args.agent_timeout is not None:
    parser.error("with proximus, set the work budget with --ak time_budget_sec=SECONDS instead of "
                 "--agent-timeout; the hard timeout follows it")

# Build every job before launching any, so a configuration error never waits behind a long run.
jobs = []
try:
    for model in args.model:
        # A Harbor job has one environment and one agent config, so tasks are grouped by both.
        groups: dict[str, tuple[EnvironmentConfig, dict, float | None, list[Path]]] = {}
        for task in tasks:
            kwargs, timeout = task_agent(task, agent, model, agent_kwargs)
            budget = kwargs.get("time_budget_sec") if proximus else None
            runtime = task_environment(task, environment, budget)
            key = json.dumps([runtime.model_dump(mode="json"), kwargs, timeout], sort_keys=True)
            groups.setdefault(key, (runtime, kwargs, timeout, []))[3].append(task)
        for runtime, kwargs, timeout, group in groups.values():
            config = build_rollout_config(
                group, agent=agent, model=model, environment=runtime,
                n_attempts=args.attempts, n_concurrent_trials=args.concurrent, verify=args.grade == "now",
                agent_kwargs=kwargs, agent_env=agent_env,
            )
            config.agents[0].override_timeout_sec = (
                args.agent_timeout if args.agent_timeout is not None else timeout
            )
            if args.verifier_timeout is not None:
                config.verifier.max_timeout_sec = args.verifier_timeout
            # Harbor's own option and agent-env checks, run here for every job rather than
            # when each job starts, so a bad --ak or --ae fails before any rollout.
            AgentFactory.run_preflight(config.agents[0])
            jobs.append((model, config, len(group)))
except (ValueError, ImportError) as e:
    parser.error(str(e))

for model, config, n_tasks in jobs:
    result = asyncio.run(run_rollouts(config))
    job_dir = config.jobs_dir / config.job_name
    print(f"{model}: {job_dir} ({n_tasks} tasks)")
    print(f"  {result.stats}")
