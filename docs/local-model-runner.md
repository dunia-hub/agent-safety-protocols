# Local model runner

The initial pilot uses `qwen2.5-coder:3b` through a local Ollama server. The research protocol and case definitions remain model independent. This adapter supports native tool calls to the existing in-memory sandbox; it has no live email, payment, calendar, or file service connection.

## Freeze before a measured run

Review and commit the scenario manifest, rubric, system prompt, tool schema, and `configs/local-qwen3b.json` before collecting results. The config specifies temperature, seed, context size, output limit, turn limit, and tool call limit. A seed is a recorded setting, not a guarantee that repeated generations are byte identical. Run on a clean commit and keep the full model digest from `check` with the evidence.

```bash
python3 -m agent_safety_pilot.model_runner check
python3 -m unittest discover -s agent_safety_pilot/tests -v
python3 -m agent_safety_pilot validate