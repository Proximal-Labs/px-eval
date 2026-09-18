"""Check the pinned images of frontier-swe-v2 tasks on Modal.

Each check boots one image in its own sandbox, runs the task's own preflight
script, and stops the sandbox. Logs land under jobs/ in the current directory.
"""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from harbor.cli.config_sources import load_config_source
from harbor.environments.base import ExecResult
from harbor.models.trial.config import EnvironmentConfig

from px_eval import check_image
from px_eval.image_checks import ImageRole
from profiles import task_environment

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("tasks_root", type=Path, help="The tasks/ directory of a frontier-swe-v2 checkout")
parser.add_argument("--environment", type=Path, required=True, help="Native EnvironmentConfig in YAML or JSON")
parser.add_argument("--task", action="append", metavar="NAME", help="Check only this task; repeatable")
parser.add_argument("--role", action="append", choices=["agent", "verifier"], help="Check only this image; repeatable")
parser.add_argument("--concurrent", type=int, default=8, help="Sandboxes to run at the same time")
parser.add_argument("--timeout", type=int, default=1800, help="Preflight timeout per image, in seconds")
args = parser.parse_args()

tasks: list[Path] = sorted(path.parent for path in args.tasks_root.glob("*/task.toml"))
if args.task:
    tasks = [task for task in tasks if task.name in args.task]
if not tasks:
    parser.error(f"no task directories with task.toml under {args.tasks_root}")
roles: list[ImageRole] = ["agent", "verifier"]
if args.role:
    roles = args.role
environment = EnvironmentConfig.model_validate(load_config_source(args.environment), extra="forbid")
run_dir = Path("jobs") / f"preflight-{datetime.now():%Y-%m-%d__%H-%M-%S}"

checks: list[tuple[Path, ImageRole]] = [(task, role) for task in tasks for role in roles]


def logs_dir(task: Path, role: ImageRole) -> Path:
    return run_dir / f"{task.name}-{role}"


def check_environment(task: Path) -> EnvironmentConfig:
    """The task's runtime profile, with the sandbox lifetime capped so a crashed run cannot
    leave sandboxes up for Harbor's 24 h default."""
    runtime = task_environment(task, environment)
    runtime.kwargs["sandbox_timeout_secs"] = args.timeout + 300
    return runtime


async def check_all() -> list[ExecResult | BaseException]:
    slots = asyncio.Semaphore(args.concurrent)

    async def check(task: Path, role: ImageRole) -> ExecResult:
        async with slots:
            return await check_image(task, role, environment=check_environment(task),
                                     logs_dir=logs_dir(task, role), timeout_sec=args.timeout)

    return await asyncio.gather(*(check(task, role) for task, role in checks), return_exceptions=True)


results = asyncio.run(check_all())

failures = 0
for (task, role), result in zip(checks, results):
    if isinstance(result, BaseException):
        status = f"error: {result!r}"
    elif result.return_code != 0:
        status = f"preflight exit {result.return_code}, see {logs_dir(task, role) / 'agent'}"
    else:
        status = "ok"
    failures += status != "ok"
    print(f"{task.name:<44} {role:<9} {status}")
print(f"{len(checks) - failures} ok, {failures} failed; logs under {run_dir}")
raise SystemExit(1 if failures else 0)
