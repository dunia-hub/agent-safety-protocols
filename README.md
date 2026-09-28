# Agent Safety Protocols

Open research led by Fatuma Yattani at Dunia Hub. This repository can hold multiple AI safety evaluation protocols. Its first study asks how to verify whether a tool-using AI agent stays within the authority granted for a task.

**Current stage:** [research protocol](paper/protocol.md). No AI model has been evaluated and no empirical safety finding is claimed. Synthetic cases, the sandbox, independent review, and the paper will be added through public pull requests.

The protocol defines a model-agnostic evidence packet and separates unauthorized attempts, blocked calls, actual effects, safe escalation, and task success. The first pilot will compare what a reviewer can determine from a final outcome with what they can determine from a complete action trace. Geography is not a study variable; later adaptations may test other languages, domains, or organizations with separate validation.

See the [research roadmap](docs/roadmap.md) for the planned PR sequence and the [decision log](docs/decisions.md) for scope and evidence rules. The target is an accurately labeled preprint by 20 October 2026. If model runs or independent review are incomplete, the first release will be a methods protocol rather than a paper with unsupported results.

The repository is public for review and discussion. Candidate fixtures and code will be labeled clearly as such when introduced. A license and data release terms will be selected before distributing model traces or a dataset.
