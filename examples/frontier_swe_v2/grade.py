"""Grade finished frontier-swe-v2 rollouts in the tasks' own verifier sandboxes.

Each source job gets one new Harbor job under jobs/ in the current directory.
The new job copies the recorded agent outputs and artifacts and runs the verifier image on them.
The source job stays unchanged, so you can grade a job again.
"""

import argparse
import asyncio
from pathlib import Path

from harbor.cli.config_sources import load_config_source
from harbor.models.job.config import JobConfig
from harbor.models.trial.config import EnvironmentConfig

from px_eval import build_grading_config, run_grading
from profiles import task_environment

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("tasks_root", type=Path, help="The tasks/ directory of a frontier-swe-v2 checkout")
parser.add_argument("job_dirs", type=Path, nargs="+", metavar="JOB_DIR", help="Rollout job directory under jobs/")
parser.add_argument("--environment", type=Path, required=True, help="Native EnvironmentConfig in YAML or JSON")
parser.add_argument("--concurrent", type=int, default=1, help="Verifier sandboxes to run at the same time")
parser.add_argument("--verifier-timeout", type=int, metavar="SECONDS",
                    help="Ceiling for the verifier phase; shorter task timeouts stay")
args = parser.parse_args()

environment = EnvironmentConfig.model_validate(load_config_source(args.environment), extra="forbid")

for job_dir in args.job_dirs:
    source = JobConfig.model_validate_json((job_dir / "config.json").read_text())
    tasks = [args.tasks_root / task.path.name for task in source.tasks]
    # rollout.py puts only tasks with one runtime profile in a job, and a Harbor job has one environment.
    profiles = (task_environment(task, environment) for task in tasks)
    runtimes = {runtime.model_dump_json(): runtime for runtime in profiles}
    if len(runtimes) != 1:
        parser.error(f"{job_dir}: the tasks have {len(runtimes)} runtime profiles, expected 1")
    [runtime] = runtimes.values()
    config = build_grading_config(job_dir, tasks, environment=runtime, n_concurrent_trials=args.concurrent)
    if args.verifier_timeout is not None:
        config.verifier.max_timeout_sec = args.verifier_timeout
    result = asyncio.run(run_grading(config))
    print(f"{job_dir}: {config.jobs_dir / config.job_name}")
    print(f"  {result.stats}")
