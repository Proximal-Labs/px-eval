# px-eval

A minimal runner for [Harbor](https://pypi.org/project/harbor/) tasks. This package adds functions to run
rollouts, to grade rollouts and to check task images. The `examples/` folder shows how to run
[frontier-swe-v2](https://github.com/Proximal-Labs/frontier-swe-v2) with them.

## Install

Requires Python 3.12 or later and `uv`.

```sh
uv sync
```

## Credentials

The runner reads no credential files. Export these variables in your shell before you run:

- `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` for Modal.
- The API key of your model provider. The `claude-code` agent reads `ANTHROPIC_API_KEY`.

## Runtime configuration

Each run takes a native Harbor `EnvironmentConfig` as a YAML or JSON file. Copy
`examples/frontier_swe_v2/environment.example.yaml` and fill in the values:

- `kwargs.registry_secret` names the Modal secret that can pull the task images.
- `kwargs.keepalive: null` keeps the image entrypoint, so the task's sandbox timer starts.
- `extra_allowed_hosts` lists the hosts that your agent installer and model provider need. The tasks deny all other egress.
- `env` sets variables in the sandbox.

The example scripts apply each task's `job.yaml` profile on top of this file and set `TASK_BUDGET_SECS` from the task's agent budget.

## Run frontier-swe-v2

Clone the task repository. Then check the images and run the tasks:

```sh
uv run python examples/frontier_swe_v2/preflight.py /path/to/frontier-swe-v2/tasks \
  --environment environment.yaml
uv run python examples/frontier_swe_v2/rollout.py /path/to/frontier-swe-v2/tasks \
  --environment environment.yaml --agent "$AGENT" --model "$MODEL"
```


`--verifier-timeout` can be used for a smoke run.

## Grading

Each rollout is graded in a separate sandbox from the task's verifier image. The agent sandbox is never used
for grading. The functions reject a task that does not have a separate verifier environment.

- `--grade now` (the default) grades each rollout immediately after its agent stops.
- `--grade later` only runs the agents. To grade the finished rollouts, run `grade.py` on their job directories:

```sh
uv run python examples/frontier_swe_v2/grade.py /path/to/frontier-swe-v2/tasks jobs/<job> \
  --environment environment.yaml
```

`grade.py` writes a new job and does not change the source job. Thus, you can grade a job again,
for example after a verifier change.

### Move /app as a Modal snapshot

Harbor usually downloads the `/app` artifact to this computer and uploads it into the verifier sandbox.
To keep `/app` on Modal, set this in your environment file:

```yaml
import_path: px_eval.modal_snapshot:SnapshotModalEnvironment
```

The agent sandbox copies `/app` with the artifact's excludes and snapshots the copy. The trial keeps only the
snapshot's Image ID in `artifacts/app/.px-modal-snapshot.json`. The verifier sandbox mounts the snapshot at `/app`.
The snapshots do not expire, and grading later uses the same snapshot.

## Test on Modal

`examples/modal_smoke` has a sample task and a script that runs a rollout and grades it now and later.
See its README.

## Tests

```sh
uv run python -m unittest discover -s tests
```

