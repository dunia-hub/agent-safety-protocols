# Research roadmap

The work will be reviewed incrementally. Each PR should state what evidence exists, what remains untested, and how its changes were checked. Progress is determined by review and evidence gates.

| PR | Scope | Review gate |
| --- | --- | --- |
| 1 | Research question, literature, protocol, limitations, roadmap, and decision log | Source claims verified; no empirical claim |
| 2 | Twelve candidate synthetic cases, variants, and explicit permission manifests | Each case has a safe path, forbidden probe, and version; freeze before measured runs |
| 3 | In-memory sandbox, event schema, deterministic oracle, fixture checks, CI | Known allowed, blocked, attempted, and effectful actions labeled correctly |
| 4 | Local model adapter and frozen run configuration | Exact model/scaffold metadata, no live side effects, repeatable run procedure |
| 5 | Model pilot with recorded runs, errors, exclusions, and checked traces | Denominators explicit; scripted fixtures never counted as model data |
| 6 | Independent outcome/trace review and disagreement log | Initial labels saved before discussion; single-reviewer limit disclosed if needed |
| 7 | Reproducible analysis and tables | Every number traceable to reviewed runs; conclusions confined to pilot |
| 8 | Manuscript, release review, and public preprint | Every result backed by evidence; methods-only or empirical status labeled accurately |

The protocol and code can be reviewed before a model is available. Passing fixture checks is a measurement-harness milestone, not a model-safety result. Release an empirical paper only when its evidence gate is met; a methods protocol can be published separately while the pilot continues.
