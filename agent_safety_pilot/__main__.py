"""Minimal CLI for inspecting the synthetic measurement fixtures."""

import json
import sys

from .harness import load_cases, run_fixture


def main() -> int:
    cases = load_cases()
    if len(sys.argv) == 2 and sys.argv[1] == "validate":
        for case in cases:
            for variant in case["variants"]:
                for actor in ("careful", "unsafe", "escalating"):
                    packet = run_fixture(case, variant, actor)
                    assert packet["oracle"]["task_success"]
        print("Validated 12 case families and 72 deterministic fixture traces. No model was tested.")
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "sample":
        _, _, case_id, actor, variant = sys.argv
        case = next((c for c in cases if c["id"] == case_id), None)
        if case is None:
            raise SystemExit(f"unknown case: {case_id}")
        print(json.dumps(run_fixture(case, variant, actor), indent=2, sort_keys=True))
        return 0
    print("Usage: python -m agent_safety_pilot validate | sample CASE_ID ACTOR VARIANT", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
