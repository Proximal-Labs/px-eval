# frontier-swe-v2 example

These scripts show how to use `px_eval` with the frontier-swe-v2 tasks.

## Before you start

1. Clone the task repository: <https://github.com/Proximal-Labs/frontier-swe-v2>.
2. Copy `environment.example.yaml` to a file of your own and fill in the values.
3. Export the credentials for your model provider and for Modal.

All scripts take the `tasks/` directory of the clone as their first argument.
All scripts write their outputs under `jobs/` in the current directory.
All scripts apply each task's `job.yaml` runtime profile on top of your configuration file, and set `TASK_BUDGET_SECS` to the task's agent budget
(for Proximus, its work budget).
The rollout script runs one Harbor job per model, runtime profile and agent configuration, one job after another;
`--concurrent` applies within each job.

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

WARNING: A full rollout runs for hours and costs money. Use `--agent-timeout` and `--verifier-timeout` for a smoke run
(with Proximus, `--ak time_budget_sec` instead of `--agent-timeout`).

```sh
uv run python examples/frontier_swe_v2/rollout.py /path/to/frontier-swe-v2/tasks \
  --environment environment.yaml --agent "$AGENT" --model "$MODEL_A" --model "$MODEL_B"
```

Each model gets one or more Harbor jobs under `jobs/` (one per runtime profile and agent configuration).
The script prints the job directory and the job stats.
The stats name each trial with its reward and any exception.
The script stops at the first job that does not launch.
Use `--task NAME` to run one task. Use `--attempts N` for repeated rollouts.
Use `--grade later` to run only the agents and grade later with `grade.py`.

## Run with Proximus

Install [`harbor-proximus`](https://github.com/Proximal-Labs/proximus) in the same environment, then pass `--agent proximus`.
The task images do not change.

```sh
uv pip install "harbor-proximus @ git+https://github.com/Proximal-Labs/proximus@6338316215b6b6d00cf6b40e6aa75007441bb4d0"
uv run python examples/frontier_swe_v2/rollout.py /path/to/frontier-swe-v2/tasks \
  --environment environment.yaml --agent proximus --model anthropic/claude-opus-5 \
  --ak time_budget_sec=7200
```

Proximus reads its options from the `[agent.proximus]` table of each task's `task.toml`.
A table under `models` adds options for one model. Harbor ignores both tables.

```toml
[agent.proximus]
task_provides_timer = true

[agent.proximus.models."anthropic/claude-opus-5"]
reasoning_effort = "max"
api_key_env = "ANTHROPIC_API_KEY"
```

`--ak KEY=VALUE` options go on top of the task's options, and `--ae KEY=VALUE` sets agent environment
variables, as in `harbor run`. Proximus reads the provider key from the agent environment first
(`--ae 'ANTHROPIC_API_KEY=${MY_KEY}'`, resolved from your shell), then from your shell. Agent options are
saved verbatim in the job files, so never put keys in `--ak` or `llm_call_kwargs`; agent environment values
are redacted there. Harbor also passes the agent environment into the sandbox; Proximus blanks the credential
and base-URL variables it uses, so the model cannot read them. Each task's `/app` artifact excludes become its `workspace_git_excludes`, so Proximus tasks
rarely share a job. `--agent` also accepts a `module:Class` path to a Proximus subclass.
The work budget `time_budget_sec` is the task's agent timeout unless you set it.
The script sets `TASK_BUDGET_SECS` to the work budget and the hard agent timeout to `harbor_proximus.hard_timeout_sec`
(the work budget plus the submission and restore limits and a margin, 1200 seconds by default), so Proximus can
submit and restore its winning commit before Harbor stops it.
For a smoke run, use `--ak time_budget_sec=600`; `--agent-timeout` is rejected with Proximus.

### Proximus options

Every option can go in `[agent.proximus]`, in a `models` table, or in `--ak`.
`harbor agent schema harbor_proximus:Proximus` prints the same list.

| Option | Default | What it does |
|---|---|---|
| `time_budget_sec` | task's agent timeout (set by this script) | Total work time. The run stops when it is used up. |
| `task_provides_timer` | `true` when the task ships `sandbox_timer.sh` (set by this script) | Points the model to the task's own timer instead of adding a second clock. |
| `workspace_git_excludes` | the task's `/app` artifact excludes (set by this script) | Paths submissions never commit, in `.gitignore` syntax. Setting it replaces the task's excludes. |
| `submission_timeout_sec` | `600` | Seconds allowed for one submission's git work. |
| `auto_submit_on_exit` | `true` | Saves unsubmitted work as a final submission when the run ends. |
| `restore_on_exit` | `true` | Checks out the winning submission when the run ends, so the verifier sees it. |
| `finalize_only_on_submit` | `false` | Does the exit submit and restore only if the model confirmed a submission. |
| `max_turns` | none | Maximum loop iterations. Reaching it ends the run like a time-out. |
| `reasoning_effort` | provider default | Passed to LiteLLM as `reasoning_effort`. See the notes below. |
| `max_thinking_tokens` | none | Passed to LiteLLM as an Anthropic thinking budget (at least 1024). Cannot be combined with `reasoning_effort`. See the notes below. |
| `temperature` | provider default | Sampling temperature. |
| `api_key_env` | provider's usual variable | Name of the variable that holds this model's key, never the key itself. |
| `api_base` | provider default | Base URL of the model API. |
| `llm_call_kwargs` | `{}` | Extra arguments for every model request, such as `max_tokens` or `extra_body`. They win over all other request settings. |
| `model_info` | LiteLLM registry | Context limit, vision support and prices for the run's model. Needs a positive `max_input_tokens` for a model LiteLLM does not know. |
| `litellm_model_info` | `{}` | The same, keyed by model name, for several models. |
| `enable_summarize` | `true` | Summarizes the conversation near the context limit. When off, a full context ends the run with an error. |
| `compaction_threshold` | `0.85` | Fraction of the context limit at which the conversation is summarized. |
| `disallowed_tools` | `[]` | Tools to remove: `list_submissions` or `view_image`. `bash` and `submit` are always available. |
| `prompt_template_path` | none | Jinja2 template around the task instruction. It must contain `{{ instruction }}`. |

Values in `--ak` are parsed as in `harbor run`, for example `--ak max_turns=200` or
`--ak 'llm_call_kwargs={"max_tokens": 32000}'`.

Notes on reasoning options. Proximus passes both to LiteLLM unchanged; LiteLLM and the
provider decide what happens to them.

- Claude 5 models take `reasoning_effort`, which LiteLLM sends as adaptive thinking with an
  effort level. They reject `max_thinking_tokens`, a fixed thinking budget, with
  `"thinking.type.enabled" is not supported for this model`. Use `max_thinking_tokens`
  only for Anthropic models that accept a fixed thinking budget.

- On an OpenAI-compatible route that LiteLLM does not know as a reasoning model (for
  example a self-hosted endpoint under `openai/`), LiteLLM drops `reasoning_effort`
  without an error. Send it in the request body instead:

  ```sh
  --ak 'llm_call_kwargs={"extra_body": {"reasoning_effort": "high"}}'
  ```

`workspace_git_excludes` replaces the excludes taken from the task's `/app` artifacts; it does
not add to them. To keep those too, list them in your value, for example
`--ak 'workspace_git_excludes=["**/node_modules/**", "**/.venv/**", "scratch/"]'`.

## Grade rollouts

The grading script grades the finished trials of one or more rollout jobs. Each trial gets a new sandbox from
the task's verifier image. The script copies the recorded agent outputs and artifacts into this sandbox.

```sh
uv run python examples/frontier_swe_v2/grade.py /path/to/frontier-swe-v2/tasks \
  jobs/<job-a> jobs/<job-b> --environment environment.yaml
```

Each source job gets one new Harbor job under `jobs/`. The source job does not change.
Use `--concurrent N` and `--verifier-timeout SECONDS` as with the rollout script.
