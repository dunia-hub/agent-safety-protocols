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

The protocol is a research design. **No model has been evaluated and no empirical safety result is claimed yet.** Its twelve task families are candidates until their fixtures and boundaries are frozen. Scripted checks of the sandbox will validate the measurement tools; they will not count as model results. This section will link to the case set, recorded runs, review data, analysis, and paper when each is available.

## Repository guide

- [`paper/protocol.md`](paper/protocol.md) — research questions, method, rubric, limitations, and sources.
- [`docs/decisions.md`](docs/decisions.md) — dated decisions and changes to the method.
- [`docs/roadmap.md`](docs/roadmap.md) — build order and review gates.

The protocol can be read now. Execution instructions and data formats will be documented alongside the runnable tools and released data; there is no model runner in this repository yet.

## Interpretation and reuse

This work develops an **evaluation method**, not a safety certification for a model. A small synthetic study cannot establish a deployment-wide failure rate. Comparisons across models or translated cases require separately validated conditions. Public material will use synthetic data and distinguish proposed methods, fixture checks, model observations, and reviewer judgments.

A license and data release terms have not yet been selected. They will be stated explicitly before code, cases, or traces are released for reuse.