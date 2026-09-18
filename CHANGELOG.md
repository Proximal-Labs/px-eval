# Changelog

## 0.1.0 (unreleased)

First release, prepared for frontier-swe-v2.

- `build_rollout_config` and `run_rollouts` build and run one Harbor job for local task directories and one agent and model. Verification is on by default.
- `check_image` boots one task image as a trial would, runs the task's preflight script and returns Harbor's `ExecResult`.
- `examples/frontier_swe_v2`: `preflight.py` checks every task image, `rollout.py` runs the tasks for one or more models. Both apply each task's `job.yaml` runtime profile.
- Validated on 2026-09-19: 68 of 68 image preflights pass, and 34 five-minute rollouts run through the verifier.
