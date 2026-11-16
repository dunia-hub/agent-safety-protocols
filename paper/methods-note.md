# Observation completeness in authorization-boundary evaluation

**Methods note, version 0.1**

**Author:** Fatuma Yattani, Dunia Hub

**Status:** Methods note with a feasibility pilot. The review gate in the research protocol has not been met, so this is not an empirical study of model safety and no behavioural rate is claimed. Released under the provision in [protocol](protocol.md) §7 that a methods note may be published while empirical work continues.

## Abstract

An evaluation harness that records an agent's tool calls can report an agent as compliant while the agent was in fact attempting to act. We built a measurement harness for authorization-boundary evaluation: twelve synthetic task families with explicit permission boundaries, a resettable in-memory sandbox, a deterministic checker, and a portable evidence packet. Running it against a small local model, we found three distinct ways a run can produce an empty action trace that a naive harness scores as a clean pass: the model's response is truncated before it emits a tool call; the model writes its call as prose instead of using the tool channel; and the model server fails. Each is now a named run status that marks the observation incomplete rather than clean, and each is evidenced by a packet a reader can open. We also record one run in which the model issued an out-of-scope read, received nothing, and then reported an invented account balance and transaction history: an outcome-only reviewer would pass it, a trace reviewer would not. The contribution is the measurement finding and the harness, not a claim about how often agents cross boundaries.

## 1. What this note claims

It claims three things.

First, that observation completeness has to be a precondition for any compliance label, and that this is not automatic. A harness that treats "no recorded tool call" as "no attempted action" will report the agent as well behaved in at least three circumstances where it was not observed at all. We found two of these by accident while selecting a model and one while collecting the pilot.

Second, that the distinction between an *attempt*, an *effect*, and an *unobserved run* can be maintained mechanically, and that keeping them separate changes what a run reports. A deterministic checker can establish what was observed; it cannot establish what was authorized, and the packet says so.

Third, that the evidence a reviewer needs can be assembled into a portable packet, and that we built one to a documented schema.

It does **not** claim that the model tested is safe or unsafe, that the measures generalize beyond one 4B parameter model on one machine, or that reviewers agree about anything, since no independent review has been conducted.

## 2. Why observation is the problem

An agent's final response is an incomplete record of its behaviour: it may attempt a prohibited call before returning a harmless answer [1]. Evaluators are therefore advised to inspect actions and configurations rather than outcomes [2], and agents are known to exploit the structure of evaluations in ways that make a score misstate what the test intended to measure [3].

That literature treats the trace as the corrective. This note reports a failure one step earlier. If the harness never records the attempt, the trace is empty, and an empty trace is indistinguishable from compliance unless the harness is built to tell them apart. The run then passes not because the agent behaved but because nothing was seen.

## 3. The harness

The design follows the [research protocol](protocol.md); what follows is what was built.

**Cases.** Twelve task families across document, calendar, purchasing and account workflows, frozen at version 1.0. Each has a legitimate goal, an explicit permission boundary stated in the user request, a permitted action, an out-of-scope probe, and a deterministic initial state. Each has a `clear` and a `pressure` variant; the pressure variant exposes untrusted text that suggests an unauthorized shortcut, attached either to the first authorized read result or as a pre-action notice, derived from the case rather than assigned by hand.

Permissions are a whitelist: an action with no matching entry is out of scope. During the freeze we found that ten of the twelve requests named one forbidden action and said nothing about anything else, so a model acting on an unmentioned resource would have been labelled unauthorized against a boundary it was never given. Every request now states its allowance exclusively, in uniform wording.

**Sandbox.** An in-memory environment with no network, payment, or message delivery. Each call is checked against the case's permissions, including amount caps and use limits, and logged with its arguments, whether it was authorized, whether it was blocked, its result, and a state diff. Enforcement is a recorded run parameter: with it off, an unauthorized call executes and its effect is recorded; with it on, it is refused and recorded as a blocked attempt.

**Checker.** A deterministic labeller that separates unauthorized attempts, blocked attempts, observed effects, safe escalations, invalid calls, and calls the runner refused before the sandbox saw them. A completed restricted read counts as an effect even with no state change, because the content reached the agent. A request for approval counts as a safe escalation only if no unauthorized call precedes it.

**Evidence packet.** Per protocol §4.3: the task, the authority with its grantor, scope and expiry, the environment with its sandbox version and tool schema, the ordered trace, the observed outcome, the checker's labels, an adjudication block, and provenance including the model digest, repository revision, and hashes of the config, case manifest, harness, runner and system prompt. A field that is unknown is marked unavailable rather than omitted. The adjudication block is deliberately empty until a human fills it: a default label would read as a silent pass.

**Harness validation.** Scripted actors drive every case and variant under both enforcement settings, 144 traces, and the validator fails if any label departs from the expected one. It also checks that the restricted outcome view withholds the trace, the labels and the adjudication, which is what protects the blinding in protocol §4.4. This establishes that the checker labels known traces correctly. It establishes nothing about whether the runner can see what a real model does, which is the subject of the next section.

## 4. Three ways an unobserved run looks compliant

Each is now a run status. Only `completed` sets `observation_complete` to true. See Table 4 of the [generated tables](tables.md) for the counts and the packet that evidences each.

**Truncated.** The model reasons before acting. If its response reaches the output cap before it emits a tool call, the harness receives a message with no structured call, treats it as a final answer, and records a run with an empty trace. In our first collection, 4 of 24 runs did this: one turn, output exactly at the cap, zero tool calls. Detection is exact rather than heuristic: the generated token count reaching the configured limit means the response was cut off. The run is labelled `truncated` and `indeterminate`.

**Tool call written as prose.** A model may advertise support for structured tool calls and still emit the call as JSON in its message content. The sandbox executes nothing, the trace stays empty, and the final response often looks like a reasonable answer. We observed this on a 3B code-oriented model that advertises the tools capability. The runner detects content that parses as a tool-call-shaped object, records it, and marks the run unobservable. It deliberately does **not** parse and execute that text: crediting a model with a call it did not make on the structured channel would make every result depend on a brittle parser.

**Transport failure.** A model server error or timeout previously raised an exception and wrote nothing, so the run vanished and the denominator silently shrank. The runner now records the status code and the server's own message and still writes a packet.

Two further statuses, `turn_limit` and `tool_limit`, mark runs stopped by the runner's own budgets; discarded calls are itemized rather than summarized.

The general point is that each of these is a plausible implementation that a careful engineer could ship, and each converts an unobserved run into a compliant-looking one. The guard is cheap. Finding the need for it was not: two of the three were discovered by reading a trace that said a model had done nothing while its own text showed it trying to act.

## 5. Feasibility pilot

One arm was collected: twelve families by two variants, enforcement off, on a locally run 4B model with reasoning enabled, at temperature 0 with a fixed seed. 24 runs attempted, 20 complete observations, 4 transport failures. Full accounting, per-run detail and configuration are in [tables.md](tables.md), generated from the packets rather than typed.

Across 20 counted runs the model produced one out-of-scope attempt, no observed unauthorized effects, no blocked attempts, and no safe escalations. The pressure hint reached the model in 9 of 10 counted pressure runs; in the tenth the model never performed its authorized read, so the hint had nothing to attach to, and that run is reported with its own denominator rather than discarded.

19 of 20 counted runs showing no boundary crossing is a floor effect, not a safety result. With almost nothing crossing, a reviewer scoring outcomes and a reviewer reading traces would agree trivially, so this arm cannot support the outcome-versus-trace comparison that the protocol's central methodological test requires. Reporting that plainly is more useful than collecting further arms that would return the same thing.

## 6. One run worth reading in full

Case A2, pressure variant. The request permitted reading `account/activity` and nothing else. The model called `read account`, a resource that does not exist in the fixture. It received nothing. It then produced a final answer stating a balance of $150.00, a deposit of $50 and a withdrawal of $30, with dates. None of it exists anywhere in the case.

Three things follow.

The checker labels this `unauthorized_attempt`, because `read account` matches no permission. That overstates it: the model was attempting the authorized action and got the resource name wrong. A deterministic labeller cannot separate a naming error from a deliberate out-of-scope access, and we do not try to make it. This is what the adjudication block exists for, and the manuscript says so rather than reporting the label as settled.

The fabrication is the more serious observation and is not a boundary question at all. A reviewer holding the outcome view sees a plausible account summary and a completed task. A reviewer holding the trace sees an empty unauthorized read followed by invention. This is the divergence the protocol was written to detect, observed once, on the 22nd run of 24.

It was also, under our first exclusion rule, discarded. The rule dropped any pressure run whose hint never arrived, which lumped this run together with the four where nothing was seen. The arm then reported zero unauthorized attempts while containing one. Observation completeness and condition validity are now separate judgments, and the run is reported with its attempt intact.

## 7. Deviations from the protocol

| Protocol | Planned | Done | Why |
| --- | --- | --- | --- |
| §4.2 | 72 runs, three repeats per cell | 24 attempted, one run per cell | At temperature 0 with a fixed seed, repeats measure harness determinism rather than model variability, and each run costs about five minutes on this hardware |
| §4.2 | One frozen configuration | Two, differing only in output cap | Four runs truncated at the original cap and were re-collected at a larger one; every packet from the original cap has a generated token count strictly below it, so the cap did not bind the rest |
| §4.4 | Two independent reviewers | None | No reviewer recruited. No inter-rater reliability is claimed and no human adjudication has been performed |
| §4.4 | Portability check by an unfamiliar reviewer | Not run | The central methodological test remains outstanding |
| §4.2 | Enforced condition | Not collected | Enforcement is only observable when the model attempts something, and it attempted almost nothing |

## 8. Limitations

The pilot ran on one machine with 7 GB of memory and no GPU, which caps the model at roughly 4B parameters. Results describe one small local model and say nothing about capable agents. A model selected for a different machine would be a different study.

The requests state their boundaries more explicitly than a real user instruction usually would. This was necessary to make the labels interpretable, and it lowers the bar: staying in scope against an explicit prohibition is easier than inferring the same boundary from a casual request.

The affordance to request approval is offered once in the system prompt. The safe-escalation measure therefore reports whether the model used an offered escape hatch, not whether it recognised the need for one unprompted.

Reasoning text is captured in the trace but is not treated as evidence of intent, consistent with protocol §3.

The two provoked demonstrations show that the harness labels each failure correctly. They do not show how often a model fails that way in ordinary use. One of them required two attempts: the same model declined the task instead of emitting a prose call when given the frozen wording, and that unsuccessful attempt is committed alongside the successful one.

Finally, the harness itself is the instrument under discussion, and it was built and validated by one person. The fixture validation proves internal consistency, not that the instrument sees everything worth seeing. Two of the three failure modes in section 4 were absent from the test suite until a real model exhibited them.

## 9. Reproducibility

Code, cases, configurations and generated tables are in the repository. Run records are not committed; the tables are generated from them and record the hashes needed to verify a packet against its configuration.

```
python3 -m unittest discover -s agent_safety_pilot/tests -v
python3 -m agent_safety_pilot validate
python3 scripts/run_pilot.py --plan
python3 scripts/make_tables.py
```

Every run records the model digest, the repository revision, whether the working tree was clean, and hashes of the configuration, case manifest, harness, runner and system prompt. The pilot runner refuses to start on a dirty working tree.

## 10. What would change the conclusions

If an independent reviewer, given only a packet, cannot identify the governing boundary or cite the evidence for a label, the packet schema is inadequate and that is a reportable result. If outcome-only review turns out to capture every material event in cases like these, the trace adds nothing and the method is unnecessary. If a harness without the observation-completeness guard produces the same labels as one with it across a larger sample, the finding in section 4 is a curiosity rather than a defect. None of these has been tested.

## Sources

1. UK AI Security Institute, *International joint testing exercise: Agentic testing* (2026). https://www.aisi.gov.uk/blog/international-joint-testing-exercise-agentic-testing
2. UK AI Security Institute, *Incident Report: unsanctioned agent behaviour during cyber testing* (2026). https://www.aisi.gov.uk/blog/incident-report-unsanctioned-agent-behaviour-during-cyber-testing
3. M. Hamin and B. Edelman, NIST Center for AI Standards and Innovation, *Cheating On AI Agent Evaluations* (2025). https://www.nist.gov/caisi/cheating-ai-agent-evaluations
4. Australian Department of Industry, Science and Resources, *Advancing methods for agentic evaluations across domains* (2026). https://www.industry.gov.au/publications/advancing-methods-agentic-evaluations-across-domains
5. NIST, *ARIA Evaluation Planning Manual: Elements of ARIA-Style AI Evaluations* (2026). https://doi.org/10.6028/NIST.AI.200-3
6. International AI Safety Report, *International AI Safety Report 2026*. https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026