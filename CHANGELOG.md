# Changelog

## Unreleased

- `build_grade_config` and `run_grades` grade a recorded rollout job: each recorded trial is re-verified in a fresh verifier environment with Harbor's native regrade. The agent is not re-run and the source job is not modified.
- `build_rollout_config` accepts `agent_kwargs`, passed to the agent unchanged. A custom agent can be given as an import path in `agent`.
- `run_job` runs any job built by this package. `run_rollouts` remains as an alias.

## 0.1.0 (unreleased)

First release, prepared for frontier-swe-v2.

- `build_rollout_config` and `run_rollouts` build and run one Harbor job for local task directories and one agent and model. Verification is on by default.
- `check_image` boots one task image as a trial would, runs the task's preflight script and returns Harbor's `ExecResult`.
- `examples/frontier_swe_v2`: `preflight.py` checks every task image, `rollout.py` runs the tasks for one or more models. Both apply each task's `job.yaml` runtime profile.
- Validated on 2026-09-19: 68 of 68 image preflights pass, and 34 five-minute rollouts run through the verifier.
