# Changelog

## 0.1.0 (unreleased)

First release, prepared for frontier-swe-v2.

- `build_rollout_config` and `run_rollouts` build and run one Harbor job for local task directories and one agent and model. Verification is on by default, and each trial is graded immediately after its agent.
- `build_grading_config` and `run_grading` build and run a Harbor regrade job that grades the finished trials of a rollout job again. The source job does not change.
- `modal_snapshot.SnapshotModalEnvironment` moves the `/app` artifact from the agent sandbox to the verifier sandbox as a Modal directory snapshot. Only the Image ID goes through this computer.
- `examples/modal_smoke`: a sample task and a script that test a rollout and its grading end to end on Modal.
- Grading always uses the task's separate verifier sandbox. `require_separate_verifier` rejects tasks that would grade in the agent sandbox.
- `check_image` boots one task image as a trial would, runs the task's preflight script and returns Harbor's `ExecResult`.
- `examples/frontier_swe_v2`: `preflight.py` checks every task image, `rollout.py` runs the tasks for one or more models and grades now or later (`--grade`). `grade.py` grades finished rollout jobs. Both apply each task's `job.yaml` runtime profile.
- Validated on 2026-09-19: 68 of 68 image preflights pass, and 34 five-minute rollouts run through the verifier.
