# Modal smoke test

This folder has a small sample task and a script to test px-eval end to end on Modal.
The `oracle` agent runs the task's solution, so the test needs Modal credentials but no model key.
A run takes a few minutes and uses three small sandboxes.

```sh
uv run python examples/modal_smoke/run.py
```

The script does these steps:

1. It runs one rollout with `--grade now`. The verifier runs in a new sandbox immediately after the agent.
2. It grades the same rollout again with a regrade job, as `grade.py` does.
3. It prints the rewards of the two jobs. It exits with status 1 if a reward is not 1.

By default, `/app` goes from the agent sandbox to the verifier sandbox as a Modal snapshot
(`px_eval.modal_snapshot`). Use `--no-snapshot` to test Harbor's usual path through this computer.

The verifier in `task/tests/test.sh` writes one value for each check into `reward.json`:

- `separate_box`: the verifier runs from the verifier image, not from the agent image.
- `answer`: the agent's `/app/answer.txt` got to the verifier.
- `excludes`: the `node_modules` exclude of the `/app` artifact was applied.
- `app_writable`: the verifier can write in `/app`.

The test output also tells if `/app` is a mount (snapshot) or a plain directory (upload).
Read it in `jobs/<job>/<trial>/verifier/test-stdout.txt`.
