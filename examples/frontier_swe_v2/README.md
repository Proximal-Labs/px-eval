# frontier-swe-v2 example

These scripts show how to use `px_eval` with the frontier-swe-v2 tasks.

## Before you start

1. Clone the task repository: <https://github.com/Proximal-Labs/frontier-swe-v2>.
2. Copy `environment.example.yaml` to a file of your own and fill in the values.
3. Export the credentials for your model provider and for Modal.

All scripts take the `tasks/` directory of the clone as their first argument.
All scripts write their outputs under `jobs/` in the current directory.
All scripts apply each task's `job.yaml` runtime profile on top of your configuration file, and set `TASK_BUDGET_SECS` to the task's agent budget.
The rollout script runs one Harbor job per model and runtime profile.

## Check the images

The preflight script boots each pinned image and runs the task's own preflight script.

```sh
uv run python examples/frontier_swe_v2/preflight.py /path/to/frontier-swe-v2/tasks \
  --environment environment.yaml
```

Use `--task NAME` to check one task. Use `--role agent` or `--role verifier` to check one image.
Use `--concurrent N` to limit the number of sandboxes that run at the same time.
The script prints one line per image and exits with status 1 if a check fails.
The script's own report is in `jobs/preflight-<time>/<task>-<role>/agent/preflight.json`.

## Run rollouts

WARNING: A full rollout runs for hours and costs money. Use `--agent-timeout` and `--verifier-timeout` for a smoke run.

```sh
uv run python examples/frontier_swe_v2/rollout.py /path/to/frontier-swe-v2/tasks \
  --environment environment.yaml --agent "$AGENT" --model "$MODEL_A" --model "$MODEL_B"
```

Each model gets one Harbor job under `jobs/`.
The script prints the job directory and the job stats.
The stats name each trial with its reward and any exception.
The script stops at the first job that does not launch.
Use `--task NAME` to run one task. Use `--attempts N` for repeated rollouts.
Use `--grade later` to run only the agents and grade later with `grade.py`.

## Grade rollouts

The grading script grades the finished trials of one or more rollout jobs. Each trial gets a new sandbox from
the task's verifier image. The script copies the recorded agent outputs and artifacts into this sandbox.

```sh
uv run python examples/frontier_swe_v2/grade.py /path/to/frontier-swe-v2/tasks \
  jobs/<job-a> jobs/<job-b> --environment environment.yaml
```

Each source job gets one new Harbor job under `jobs/`. The source job does not change.
Use `--concurrent N` and `--verifier-timeout SECONDS` as with the rollout script.
