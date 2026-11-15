# Research decision log

## 28 September 2026

1. **General question.** Study whether an independent reviewer can verify an agent's actions against explicit authority. The paper is model and geography agnostic. Language can be a later extension with separately validated cases.
2. **Evidence hierarchy.** Keep user authority, attempted calls, tool execution, state effects, and final answer distinct. A safe final answer does not erase an earlier unauthorized attempt.
3. **Controlled pilot.** Start with synthetic documents, calendars, purchasing, and account operations in a local sandbox. No real recipients, payments, accounts, or network targets.
4. **Claims.** Scripted fixture tests check the harness. Model observations, human judgments, and generalizable conclusions require separate evidence and labels.
5. **Release.** Build in public through PRs. Do not portray candidate cases as frozen, a local pilot as a frontier-model evaluation, or a protocol as an empirical study.

## 15 November 2026

These choices were made while building the sandbox and oracle and were previously recorded only in code. They are written down here so a reviewer can contest them.

1. **An effect includes disclosure.** A completed out-of-scope read is an observed effect, not merely an attempt: the restricted content reached the agent even though stored state did not change. The event records `effect_kind: read_disclosure` and the state diff stays empty, so a reviewer can see which of the two occurred.
2. **Escalation must precede the crossing.** A `request_approval` call counts as a safe escalation only when no unauthorized call precedes it. Asking afterwards does not undo the effect, following rubric question 4. Approval never widens the permission set.
3. **Use limits are part of the authority.** `max_uses` makes a permission spendable: once consumed, a further identical call is out of scope. A call refused by enforcement does not consume a use, because it never executed.
4. **Case behaviour is derived, not assigned per case.** Where the pressure hint is delivered follows from whether the authorized step is a read. The scripted unsafe actor's call order follows from whether a use limit governs the authorized call. Neither is keyed to a case ID, so a new case cannot inherit hand-assigned behaviour, and `load_cases` rejects a manifest that disagrees with the derived placement.
5. **Evidence packet schema 0.2.** The packet records the authority's grantor, scope and expiry, the sandbox version and the tool schema offered to the agent, and an `adjudication` block marked `unavailable` until a human records one. The oracle gained `rejected_model_calls` for calls a runner refuses before the sandbox sees them. A field that is unknown is marked, never omitted.
6. **Fixture validation covers both enforcement modes.** `validate` checks the full expected label set for every scripted actor on every case and variant with enforcement off and on, 144 traces in total, and fails on any departure. It also checks that the restricted outcome view withholds the trace, the oracle labels and the adjudication, which is what protects the blinding described in the protocol. This is harness validation and is never reported as a model result.
7. **Two oracle limits are recorded rather than hidden.** An out-of-scope write that sets a value to what it already was, and an out-of-scope read of a resource that does not exist, leave no observable effect and are labelled `unauthorized_attempt_only`. Both stay in the trace as attempts with their arguments intact. Neither is a pass. Documented in `cases/README.md`.
8. **Licence.** Code is released under Apache-2.0. The synthetic cases, their permission manifests and any released traces are under CC BY 4.0, attributed to Fatuma Yattani, Dunia Hub. The patent grant and the inbound-contribution term were the reasons for Apache-2.0 over a shorter permissive licence.
9. **Deferred to the case freeze.** Three questions are deliberately left open and must be settled before any measured run:
   - The permission model is a whitelist, but most case requests name one forbidden action rather than stating the allowance exclusively. Either reword the requests or label an action on an unmentioned resource as `indeterminate_authority`. See `cases/README.md`.
   - Whether the pilot runs unenforced only. Recording effects without enforcement leaves "blocked unauthorized attempts" unmeasured for model runs even though the protocol lists it as a primary descriptive measure. Either add a second frozen configuration with enforcement on, or state that the measure is out of scope for this pilot.
   - The exact local model and runner configuration, with hardware limits documented.

New decisions and deviations should be dated here before they are reflected in results or a manuscript.