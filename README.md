# Agent Safety Protocols

**Can an independent reviewer verify that an AI agent stayed within the authority it was given?**

Agent Safety Protocols is an open research project led by Fatuma Yattani at [Dunia Hub](https://github.com/dunia-hub). It develops practical ways to specify an agent's permissions, record its actions, and judge what happened from evidence another person can inspect. The method is intended to work across models, tools, domains, languages, and locations, with each adaptation checked on its own terms.

## The problem

An agent may finish a legitimate task while taking an unauthorized step along the way: reading an unrelated file, attempting to contact an unapproved recipient, changing an account setting, or placing an order before approval. A final answer or task-success score may not show that step. A useful evaluation must preserve the authority granted **before** the run and the actions attempted **during** it, including calls blocked by a tool.

Our research question is: **what evidence is sufficient for an independent evaluator to determine whether a tool-using agent respected an explicit authorization boundary?**

## What the project builds

| Component | Purpose |
| --- | --- |
| Synthetic cases | Give an agent a legitimate goal and a precise permission boundary in document, calendar, purchasing, or account workflows. |
| Controlled sandbox | Record calls and state changes without sending real messages, making payments, or changing real accounts. |
| Evidence packet | Preserve the request, authority, environment, ordered action trace, tool responses, state effects, and provenance. |
| Review rubric | Separate unauthorized attempts, blocked calls, actual effects, safe requests for approval, task success, and uncertainty. |
| Study and paper | Compare judgments from final outcomes with judgments from full traces, then test whether another reviewer can reproduce the assessment. |

The [research protocol](paper/protocol.md) gives the full study design, candidate cases, proposed sampling, scoring rules, limitations, and sources. Cases, code, run records, review decisions, and analysis will be added and linked here as they are validated.

## How an evaluation works

1. **Define authority.** Record what the user allowed, what requires approval, and what is out of scope before the agent runs.
2. **Run a synthetic task.** Reset the sandbox and log attempted tool calls, accepted or blocked operations, responses, and state changes in order.
3. **Build the evidence packet.** Keep the authority, execution record, final outcome, and configuration together with references to the events supporting each judgment.
4. **Review independently.** Score safety and task completion separately. Compare what can be concluded from the final outcome with what the full trace reveals.
5. **Report uncertainty.** Preserve missing observations, ambiguous authority, tool failures, exclusions, and reviewer disagreements rather than turning them into a clean pass rate.

A blocked unauthorized call is an **attempt**, not an observed effect. A completed restricted read can disclose information without changing stored state; a write or synthetic outbound action can leave another observable effect. Asking for required approval before acting can be a safe escalation. The [run-level rubric](paper/protocol.md#45-run-level-scoring-rubric) defines these judgments in detail.

## Research status and evidence

**No model has been evaluated and no empirical safety result is claimed.** What exists is the research design and the measurement harness that will collect evidence once a model adapter is in place.

| Built | State |
| --- | --- |
| Research protocol, limitations, decision log | Complete at version 0.2 |
| Twelve synthetic task families with explicit permission manifests | **Frozen at case version 1.0** |
| In-memory sandbox, event schema, deterministic oracle, evidence packet | Complete at packet schema 0.2 |
| Fixture checks and CI | 10 unit tests, plus 144 scripted fixture traces across both enforcement modes |
| Local model adapter and frozen run configuration | Not in this repository yet |

The twelve task families are frozen at version 1.0; any change to a request, permission, fixture, hint, or placement requires a new version. The scripted fixture checks establish that the harness labels known allowed, blocked, attempted, and effectful actions correctly. They are a measurement-harness milestone and are never counted as model results. This section will link to the frozen case set, recorded runs, review data, analysis, and paper when each is available.

## Repository guide

- [`paper/protocol.md`](paper/protocol.md) — research questions, method, rubric, limitations, and sources.
- [`cases/`](cases/) — the twelve task families, their permission manifests, and the freeze checklist.
- [`agent_safety_pilot/`](agent_safety_pilot/) — the measurement harness: permission matching, in-memory tools, event log, evidence packet, and deterministic oracle.
- [`docs/decisions.md`](docs/decisions.md) — dated decisions and changes to the method.
- [`docs/roadmap.md`](docs/roadmap.md) — build order and review gates.

## Running the harness

Requires Python 3.10 or newer. The harness uses only the standard library and has no network, payment, or message adapter.

```bash
python3 -m unittest discover -s agent_safety_pilot/tests -v
python3 -m agent_safety_pilot validate
python3 -m agent_safety_pilot sample D1 unsafe pressure
```

`validate` runs every case family through each scripted actor under both enforcement settings and fails if any oracle label departs from the expected one. `sample` prints a single evidence packet. Both are documented in [`agent_safety_pilot/README.md`](agent_safety_pilot/README.md).

## Interpretation and reuse

This work develops an **evaluation method**, not a safety certification for a model. A small synthetic study cannot establish a deployment-wide failure rate. Comparisons across models or translated cases require separately validated conditions. Public material will use synthetic data and distinguish proposed methods, fixture checks, model observations, and reviewer judgments.

## License

The code in this repository is licensed under [Apache-2.0](LICENSE). The synthetic cases in [`cases/`](cases/), their permission manifests, and any evidence packets released from them are licensed under [CC BY 4.0](cases/LICENSE).

Attribute as: Fatuma Yattani, Dunia Hub, *Agent Safety Protocols*.

Contributions are welcome. Please open an issue or a pull request that states what evidence exists, what remains untested, and how the change was checked, as [`docs/roadmap.md`](docs/roadmap.md) requires of every PR.

