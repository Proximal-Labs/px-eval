"""Run frontier-swe-v2 tasks with one agent and one or more models.

Tasks that share a runtime profile (your configuration plus the task's job.yaml) run in one
Harbor job per model, under jobs/ in the current directory.
"""

import argparse
import asyncio
from pathlib import Path

from harbor.cli.config_sources import load_config_source
from harbor.models.trial.config import EnvironmentConfig

from px_eval import build_rollout_config, run_rollouts
from profiles import task_environment

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("tasks_root", type=Path, help="The tasks/ directory of a frontier-swe-v2 checkout")
parser.add_argument("--environment", type=Path, required=True, help="Native EnvironmentConfig in YAML or JSON")
parser.add_argument("--agent", required=True, help="Harbor agent name")
parser.add_argument("--model", action="append", required=True, metavar="PROVIDER/MODEL",
                    help="Model for the agent; repeat for several models")
parser.add_argument("--task", action="append", metavar="NAME", help="Run only this task; repeatable")
parser.add_argument("--attempts", type=int, default=1, help="Rollouts per task and model")
parser.add_argument("--concurrent", type=int, default=1, help="Trials to run at the same time")
parser.add_argument("--grade", choices=["now", "later"], default="now",
                    help="Grade each rollout right after its agent, or later with grade.py")
parser.add_argument("--agent-timeout", type=int, metavar="SECONDS",
                    help="Cap the agent phase; useful for smoke runs")
parser.add_argument("--verifier-timeout", type=int, metavar="SECONDS",
                    help="Ceiling for the verifier phase; shorter task timeouts stay")
args = parser.parse_args()

tasks: list[Path] = sorted(path.parent for path in args.tasks_root.glob("*/task.toml"))
if args.task:
    tasks = [task for task in tasks if task.name in args.task]
if not tasks:
    parser.error(f"no task directories with task.toml under {args.tasks_root}")
environment = EnvironmentConfig.model_validate(load_config_source(args.environment), extra="forbid")

# A Harbor job has one environment, so tasks are grouped by their resolved runtime profile.
groups: dict[str, tuple[EnvironmentConfig, list[Path]]] = {}
for task in tasks:
    runtime = task_environment(task, environment)
    groups.setdefault(runtime.model_dump_json(), (runtime, []))[1].append(task)

for model in args.model:
    for runtime, group in groups.values():
        config = build_rollout_config(
            group, agent=args.agent, model=model, environment=runtime,
            n_attempts=args.attempts, n_concurrent_trials=args.concurrent, verify=args.grade == "now",
        )
        if args.agent_timeout is not None:
            config.agents[0].override_timeout_sec = args.agent_timeout
        if args.verifier_timeout is not None:
            config.verifier.max_timeout_sec = args.verifier_timeout
        result = asyncio.run(run_rollouts(config))
        job_dir = config.jobs_dir / config.job_name
        print(f"{model}: {job_dir} ({len(group)} tasks)")
        print(f"  {result.stats}")
