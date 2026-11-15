#!/usr/bin/env python3
"""Run the planned pilot sets and write a run index with explicit denominators.

Three sets, never pooled:

  primary      12 families x 2 variants, enforcement off
  determinism  6 re-runs of fixed primary cells, to show how far a fixed seed repeats
  enforced     12 families x 2 variants, enforcement on

Resumable: a run whose packet already exists is skipped, so an interrupted session
continues instead of starting over. Nothing is ever overwritten.

Usage:
  python3 scripts/run_pilot.py --plan
  python3 scripts/run_pilot.py
  python3 scripts/run_pilot.py --sets primary
  python3 scripts/run_pilot.py --index-only
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_safety_pilot import load_cases  # noqa: E402
from agent_safety_pilot.model_runner import (  # noqa: E402
    OllamaClient,
    OllamaError,
    load_config,
    provenance,
    run_case,
)

RESULTS = ROOT / "results"
PRIMARY_CONFIG = ROOT / "configs" / "local-qwen3-4b.json"
ENFORCED_CONFIG = ROOT / "configs" / "local-qwen3-4b-enforced.json"

# Fixed cells for the determinism check, chosen to cover both variants and all four
# workflows. Fixed in advance so the set cannot be picked after seeing results.
DETERMINISM_CELLS = [
    ("D1", "clear"),
    ("D3", "pressure"),
    ("C2", "clear"),
    ("P2", "pressure"),
    ("A1", "clear"),
    ("A3", "pressure"),
]


def planned_runs(cases: list[dict[str, Any]], sets: list[str]) -> list[dict[str, Any]]:
    ids = [case["id"] for case in cases]
    runs: list[dict[str, Any]] = []
    if "primary" in sets:
        runs += [
            {"set": "primary", "case": cid, "variant": v, "config": PRIMARY_CONFIG}
            for cid in ids for v in ("clear", "pressure")
        ]
    if "determinism" in sets:
        runs += [
            {"set": "determinism", "case": cid, "variant": v, "config": PRIMARY_CONFIG}
            for cid, v in DETERMINISM_CELLS
        ]
    if "enforced" in sets:
        runs += [
            {"set": "enforced", "case": cid, "variant": v, "config": ENFORCED_CONFIG}
            for cid in ids for v in ("clear", "pressure")
        ]
    for run in runs:
        run["output"] = RESULTS / run["set"] / f"{run['case']}-{run['variant']}.json"
    return runs


def shown(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise, so printing never raises."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def exclusions(packet: dict[str, Any]) -> list[str]:
    """Why this run cannot be counted as an observation. Empty means it counts."""
    reasons = []
    if not packet["oracle"]["observation_complete"]:
        reasons.append(f"incomplete observation: {packet['model_run']['status']}")
    if packet["variant"] == "pressure" and not packet["model_run"]["pressure_delivered"]:
        reasons.append("pressure hint never reached the model")
    return reasons


def summarise(packet: dict[str, Any]) -> dict[str, Any]:
    oracle = packet["oracle"]
    return {
        "case": packet["case_id"],
        "case_version": packet["case_version"],
        "variant": packet["variant"],
        "status": packet["model_run"]["status"],
        "turns": packet["model_run"]["turns"],
        "tool_calls": packet["model_run"]["tool_calls"],
        "pressure_delivered": packet["model_run"]["pressure_delivered"],
        "observation_complete": oracle["observation_complete"],
        "summary": oracle["summary"],
        "unauthorized_attempts": oracle["unauthorized_attempts"],
        "unauthorized_effects": oracle["unauthorized_effects"],
        "blocked_unauthorized_attempts": oracle["blocked_unauthorized_attempts"],
        "safe_escalations": oracle["safe_escalations"],
        "invalid_calls": oracle["invalid_calls"],
        "rejected_model_calls": oracle["rejected_model_calls"],
        "exclusions": exclusions(packet),
    }


def calls_of(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [event["call"] for event in packet["trace"] if event["kind"] == "tool_call"]


def build_index(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Read every packet that exists on disk and report per-set denominators."""
    sets: dict[str, Any] = {}
    for run in runs:
        entry = sets.setdefault(run["set"], {"planned": 0, "present": 0, "runs": []})
        entry["planned"] += 1
        if not run["output"].exists():
            continue
        packet = json.loads(run["output"].read_text())
        entry["present"] += 1
        row = summarise(packet)
        row["output"] = shown(run["output"])
        if run["set"] == "determinism":
            primary = RESULTS / "primary" / run["output"].name
            if primary.exists():
                other = json.loads(primary.read_text())
                row["repeats_primary"] = (
                    calls_of(packet) == calls_of(other)
                    and packet["outcome"]["final_response"] == other["outcome"]["final_response"]
                )
                row["repeats_primary_calls_only"] = calls_of(packet) == calls_of(other)
        entry["runs"].append(row)

    for name, entry in sets.items():
        counted = [r for r in entry["runs"] if not r["exclusions"]]
        entry["counted"] = len(counted)
        entry["excluded"] = len(entry["runs"]) - len(counted)
        entry["exclusion_reasons"] = sorted({reason for r in entry["runs"] for reason in r["exclusions"]})
        # Denominators for the descriptive measures: only counted runs.
        entry["measures"] = {
            "runs_with_unauthorized_attempt": sum(1 for r in counted if r["unauthorized_attempts"]),
            "runs_with_blocked_unauthorized_attempt": sum(1 for r in counted if r["blocked_unauthorized_attempts"]),
            "runs_with_unauthorized_effect": sum(1 for r in counted if r["unauthorized_effects"]),
            "runs_with_safe_escalation": sum(1 for r in counted if r["safe_escalations"]),
            "denominator": len(counted),
        }
        if name == "determinism":
            repeated = [r for r in entry["runs"] if "repeats_primary" in r]
            entry["determinism"] = {
                "compared": len(repeated),
                "identical_calls_and_answer": sum(1 for r in repeated if r["repeats_primary"]),
                "identical_calls_only": sum(1 for r in repeated if r.get("repeats_primary_calls_only")),
            }
    return {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sets": sets}


def write_index(index: dict[str, Any]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "index.json"
    path.write_text(json.dumps(index, indent=2) + "\n")
    return path


def report(index: dict[str, Any]) -> None:
    for name, entry in index["sets"].items():
        print(f"\n{name}: {entry['present']}/{entry['planned']} run, "
              f"{entry['counted']} counted, {entry['excluded']} excluded")
        for reason in entry["exclusion_reasons"]:
            print(f"    excluded: {reason}")
        measures = entry["measures"]
        if measures["denominator"]:
            print(f"    of {measures['denominator']} counted runs: "
                  f"{measures['runs_with_unauthorized_attempt']} with an unauthorized attempt, "
                  f"{measures['runs_with_blocked_unauthorized_attempt']} blocked, "
                  f"{measures['runs_with_unauthorized_effect']} with an observed effect, "
                  f"{measures['runs_with_safe_escalation']} with a safe escalation")
        if "determinism" in entry:
            d = entry["determinism"]
            print(f"    determinism: {d['identical_calls_and_answer']}/{d['compared']} identical calls and answer, "
                  f"{d['identical_calls_only']}/{d['compared']} identical calls")
    print("\nCounts are observations, not rates. No run is pooled across sets.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sets", nargs="+", default=["primary", "determinism", "enforced"],
                        choices=["primary", "determinism", "enforced"])
    parser.add_argument("--plan", action="store_true", help="list the planned runs and exit")
    parser.add_argument("--index-only", action="store_true", help="rebuild the index from packets on disk and exit")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="run with uncommitted changes; the packets will name a commit that is not what ran")
    args = parser.parse_args()

    cases = load_cases()
    runs = planned_runs(cases, args.sets)

    if args.plan:
        for run in runs:
            mark = "done" if run["output"].exists() else "todo"
            print(f"{mark}  {run['set']:<12} {run['case']:<3} {run['variant']:<9} "
                  f"{run['config'].name:<32} {shown(run['output'])}")
        todo = sum(1 for r in runs if not r["output"].exists())
        print(f"\n{len(runs)} planned, {todo} still to run, "
              f"about {todo * 5} minutes at five minutes a run")
        return 0

    if args.index_only:
        report(index := build_index(runs))
        print(f"\nwrote {shown(write_index(index))}")
        return 0

    metadata: dict[str, dict[str, Any]] = {}
    configs: dict[str, dict[str, Any]] = {}
    for path in {run["config"] for run in runs}:
        config = load_config(path)
        client = OllamaClient(config["endpoint"], config["timeout_seconds"])
        meta = provenance(client, config, path)
        if meta["git_dirty"] and not args.allow_dirty:
            print("refusing to run: the working tree is dirty, so git_revision would not "
                  "describe what ran. Commit first, or pass --allow-dirty.", file=sys.stderr)
            return 1
        configs[path.name] = config
        metadata[path.name] = meta
        print(f"{path.name}: {meta['model']} {meta['model_digest'][:19]} "
              f"enforcement={config['sandbox_enforcement']}")

    by_id = {case["id"]: case for case in cases}
    todo = [run for run in runs if not run["output"].exists()]
    print(f"\n{len(runs)} planned, {len(todo)} to run\n")
    for position, run in enumerate(todo, start=1):
        name = run["config"].name
        client = OllamaClient(configs[name]["endpoint"], configs[name]["timeout_seconds"])
        started = time.time()
        try:
            packet = run_case(client, by_id[run["case"]], run["variant"], configs[name], metadata[name])
        except OllamaError as exc:
            print(f"[{position}/{len(todo)}] {run['set']} {run['case']} {run['variant']}: "
                  f"aborted before any turn: {exc.reason}", file=sys.stderr)
            print("stopping. fix the server and run again; completed packets are kept.", file=sys.stderr)
            break
        run["output"].parent.mkdir(parents=True, exist_ok=True)
        run["output"].write_text(json.dumps(packet, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        reasons = exclusions(packet)
        flag = "excluded: " + "; ".join(reasons) if reasons else "counted"
        print(f"[{position}/{len(todo)}] {run['set']:<12} {run['case']:<3} {run['variant']:<9} "
              f"{packet['model_run']['status']:<24} {packet['oracle']['summary']:<30} "
              f"{time.time() - started:5.0f}s  {flag}")

    report(index := build_index(runs))
    print(f"\nwrote {shown(write_index(index))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
