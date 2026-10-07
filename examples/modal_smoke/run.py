"""Test px-eval end to end on Modal with the sample task in task/.

The oracle agent runs the task's solution, so the test needs Modal credentials but no model key.
The script runs one rollout that grades immediately, then grades the same rollout again with a regrade job.
It writes the jobs under jobs/ in the current directory and exits with status 1 if a reward is not 1.
"""

import argparse
import asyncio
from pathlib import Path

from harbor.models.job.config import JobConfig
from harbor.models.trial.config import EnvironmentConfig
from harbor.models.trial.result import TrialResult

from px_eval import build_grading_config, build_rollout_config, run_grading, run_rollouts

TASK = Path(__file__).parent / "task"

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--snapshot", action=argparse.BooleanOptionalAction, default=True,
                    help="Move /app from the agent sandbox to the verifier sandbox as a Modal snapshot")
args = parser.parse_args()

environment = EnvironmentConfig(
    type="modal",
    import_path="px_eval.modal_snapshot:SnapshotModalEnvironment" if args.snapshot else None,
    kwargs={"sandbox_timeout_secs": 900},
)


def rewards(label: str, config: JobConfig) -> list[float | None]:
    """Print the rewards of each trial of a finished job and return the main rewards."""
    job_dir = config.jobs_dir / config.job_name
    print(f"{label}: {job_dir}")
    found = []
    for path in sorted(job_dir.glob("*/result.json")):
        trial = TrialResult.model_validate_json(path.read_text())
        reward = trial.verifier_result.rewards if trial.verifier_result else None
        error = trial.exception_info.exception_type if trial.exception_info else None
        print(f"  {trial.trial_name}: rewards={reward} error={error}")
        found.append((reward or {}).get("reward"))
    return found


rollout = build_rollout_config([TASK], agent="oracle", model="oracle", environment=environment)
asyncio.run(run_rollouts(rollout))
grading = build_grading_config(rollout.jobs_dir / rollout.job_name, [TASK], environment=environment)
asyncio.run(run_grading(grading))
raise SystemExit(0 if rewards("graded now", rollout) + rewards("graded later", grading) == [1, 1] else 1)
