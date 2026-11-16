#!/usr/bin/env python3
"""Reproduce each observation failure deliberately, so the validity claims cite artifacts.

These packets are NOT pilot data. Each one is produced by a configuration chosen to
provoke a specific failure, and each is marked as a demonstration inside the packet so
it can never be mistaken for an observation of model behaviour.

They exist because the failures were first seen by accident, and those packets were
overwritten or deleted. A claim that a harness can record an attempted action as
compliance should rest on a file a reader can open, not on a note in a log.

  python3 scripts/make_demonstrations.py --plan
  python3 scripts/make_demonstrations.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_safety_pilot import load_cases  # noqa: E402
from agent_safety_pilot.model_runner import (  # noqa: E402
    COMPLETED,
    OllamaClient,
    OllamaError,
    load_config,
    provenance,
    run_case,
)

OUT = ROOT / "results" / "demonstrations"
CONFIGS = ROOT / "configs" / "demonstrations"

DEMONSTRATIONS = [
    {
        "name": "truncated",
        "case": "D1",
        "variant": "clear",
        "config": CONFIGS / "truncated.json",
        "intended_status": "truncated",
        "shows": "the response hits the output cap before emitting a tool call, so what the "
                 "model was about to do is unobservable",
        "provoked_by": "num_predict lowered to 64, far below the roughly 330 tokens this case "
                       "needs before its first call",
    },
    {
        "name": "unparsed-tool-call-text-d1",
        "case": "D1",
        "variant": "clear",
        "config": CONFIGS / "unparsed-tool-call-text.json",
        "intended_status": "unparsed_tool_call_text",
        "shows": "a model that advertises the tools capability writes its call as JSON in the "
                 "content field, so the sandbox executes nothing and the trace stays empty",
        "provoked_by": "qwen2.5-coder:3b, which advertises tools but emits calls as prose",
    },
    {
        "name": "unparsed-tool-call-text-p2",
        "case": "P2",
        "variant": "clear",
        "config": CONFIGS / "unparsed-tool-call-text.json",
        "intended_status": "unparsed_tool_call_text",
        "shows": "the same failure on the charge case, where this model was first seen writing "
                 "its call as prose",
        "provoked_by": "qwen2.5-coder:3b on P2, the case the behaviour was originally observed on",
    },
]


def run_one(demo: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    config = load_config(demo["config"])
    client = OllamaClient(config["endpoint"], config["timeout_seconds"])
    metadata = provenance(client, config, demo["config"])
    packet = run_case(client, case, demo["variant"], config, metadata)
    packet["demonstration"] = {
        "name": demo["name"],
        "not_pilot_data": True,
        "intended_status": demo["intended_status"],
        "shows": demo["shows"],
        "provoked_by": demo["provoked_by"],
        "note": "produced deliberately to evidence a failure mode; never counted as an "
                "observation of model behaviour",
    }
    return packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", action="store_true", help="list what would run and exit")
    args = parser.parse_args()

    cases = {case["id"]: case for case in load_cases()}

    if args.plan:
        for demo in DEMONSTRATIONS:
            target = OUT / f"{demo['name']}.json"
            mark = "done" if target.exists() else "todo"
            print(f"{mark}  {demo['name']:<24} {demo['case']} {demo['variant']:<8} "
                  f"{demo['config'].name:<28} expects {demo['intended_status']}")
        return 0

    failures = 0
    for demo in DEMONSTRATIONS:
        target = OUT / f"{demo['name']}.json"
        if target.exists():
            print(f"{demo['name']}: already present, skipping")
            continue
        try:
            packet = run_one(demo, cases[demo["case"]])
        except (OllamaError, ValueError) as exc:
            print(f"{demo['name']}: could not run: {exc}", file=sys.stderr)
            failures += 1
            continue
        status = packet["model_run"]["status"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(packet, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        if status == demo["intended_status"]:
            verdict = "reproduced"
        elif status == COMPLETED:
            verdict = "DID NOT reproduce: the run completed normally"
            failures += 1
        else:
            verdict = f"DID NOT reproduce: got {status}"
            failures += 1
        print(f"{demo['name']}: {verdict}")
        print(f"    observation_complete={packet['oracle']['observation_complete']} "
              f"summary={packet['oracle']['summary']} tool_calls={packet['model_run']['tool_calls']}")
        print(f"    saved {target.relative_to(ROOT)}")

    if failures:
        print(f"\n{failures} demonstration(s) did not reproduce. The packets are kept either way; "
              "a failure to reproduce is itself worth recording.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
