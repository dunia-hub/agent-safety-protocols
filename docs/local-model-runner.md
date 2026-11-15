# Local model runner

The pilot runs `qwen3:4b` through a local Ollama server. The research protocol and the case definitions stay model independent. The adapter uses native tool calls into the existing in-memory sandbox; it has no live email, payment, calendar, or file service connection, and the endpoint is pinned to `http://127.0.0.1:11434` in two places.

## Why this model

The model was chosen on evidence from this machine, not on reputation.

| Candidate | Outcome |
| --- | --- |
| `qwen2.5-coder:3b` | Advertises the `tools` capability but emits tool calls as JSON text in `content` instead of using the tool channel. Also produced wrong resource names. Rejected. |
| `qwen3:8b` | Needs 6.6 GiB; the machine has about 5 GiB free and no GPU. Ollama refuses it with HTTP 500, and at a smaller context it falls back to CPU and exceeds the timeout. Rejected. |
| `qwen3:4b` | 2.5 GB, advertises `completion, tools, thinking`, and emits correct structured calls. Selected. |

The pilot therefore runs CPU-only on 7 GB of RAM at roughly 110 seconds per model call. That is a real constraint on the study, not an incidental detail: it caps the model size, and any result must be read as an observation about one small local model rather than a statement about capable agents in general.

## Why `think` is true

`qwen3:4b` reasons before answering either way. `think` only decides where that text is reported.

- `think: true` puts the reasoning in the `thinking` field and leaves `content` holding the final answer.
- `think: false` leaves `thinking` empty and puts the reasoning into `content`.

The pilot sets `think: true`. With `think: false` the reasoning becomes the packet's `final_response`, so a blinded reviewer scoring the outcome view would be handed the model's scratchpad instead of its answer, which destroys the comparison the study is built on. Reasoning text is still captured in the trace as evidence; it is not used to infer private intent.

## Observation is not compliance

A run only counts as an observation when the runner could see what the model did. Two real failures made this necessary, both of which previously produced a clean label:

- a response truncated at the output cap, cut off before it reached a tool call;
- a response that invoked a tool in prose instead of on the tool channel.

Both now mark the run unobservable. `model_run.status` carries the reason and `oracle.observation_complete` is false:

| Status | Meaning | Counts as an observation |
| --- | --- | --- |
| `completed` | The model stopped with a final answer and nothing was cut off. | Yes |
| `truncated` | `eval_count` reached `num_predict`. Anything the model was about to do is unknown. | No |
| `unparsed_tool_call_text` | The response looks like a tool call written in prose. Recorded, never executed. | No |
| `turn_limit` / `tool_limit` | A runner limit stopped the run. Discarded calls are itemised. | No |
| `transport_error` | The model server failed. The status code and its message body are recorded and a packet is still written. | No |

A run that already crossed a boundary keeps `unauthorized_effect` even if it later truncates: the crossing was observed, only the rest of the run was not. Prose that looks like a tool call is never parsed and executed, because crediting a model with a call it did not make on the structured channel would make every result depend on a brittle parser.

## Freeze before a measured run

Review and commit the scenario manifest, rubric, system prompt, tool schema, and `configs/local-qwen3-4b.json` before collecting results. The config records the model, endpoint, `think`, temperature, seed, context size, output limit, turn limit, tool-call limit, timeout, and enforcement setting. A seed is a recorded setting, not a guarantee that repeated generations are byte identical.

`check` refuses to proceed if the configured model is not pulled locally, carries no digest, or does not advertise the `tools` capability. It also records `git_dirty` and warns when the working tree is dirty, because a revision that does not describe what ran is worse than no revision.

```bash
python3 -m unittest discover -s agent_safety_pilot/tests -v
python3 -m agent_safety_pilot validate
python3 -m agent_safety_pilot.model_runner check
python3 -m agent_safety_pilot.model_runner run D1 clear results/D1-clear.json
```

Run on a clean commit and keep the full model digest from `check` with the evidence. The runner refuses to overwrite an existing output file.

## Planned run set

Three sets, reported with separate denominators and never pooled:

| Set | Runs | Purpose |
| --- | --- | --- |
| Primary | 24 (12 families, 2 variants, 1 run each) | The pilot observations, enforcement off. |
| Determinism check | 6 re-runs from the primary set | Shows how far a fixed seed at temperature 0 actually repeats. |
| Enforced sub-study | 24 (12 families, 2 variants, enforcement on) | The only way to observe blocked unauthorized attempts, and a clear-versus-pressure comparison under enforcement. |

Three repeats of every case were dropped. At temperature 0 with a fixed seed, repeats measure the harness's determinism rather than the model's variability, so a small dedicated check answers that question and the saved time goes to the enforced set. At roughly four minutes a run, the full set is an overnight job on this hardware.

Runs excluded from a set must be reported with their reason. A pressure run where `pressure_delivered` is false never had the hint reach the model and is not a pressure observation.

## Running the set

`scripts/run_pilot.py` walks the planned runs, writes each packet to `results/<set>/<case>-<variant>.json`, and skips any that already exist, so an interrupted session resumes instead of restarting. It refuses to start on a dirty working tree.

```bash
python3 scripts/run_pilot.py --plan
python3 scripts/run_pilot.py
python3 scripts/run_pilot.py --sets primary
python3 scripts/run_pilot.py --index-only
```

It writes `results/index.json`, which reports per set how many runs were planned, how many exist, how many count as observations, and how many were excluded with the reason. The descriptive counts are computed against the counted runs only, and the three sets are never pooled. `results/` is not tracked in git.
