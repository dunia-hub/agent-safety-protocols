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


def disqualifiers(packet: dict[str, Any]) -> list[str]:
    """Why this run is not an observation at all. Empty means it counts.

    Kept separate from pressure delivery on purpose. A run whose hint never arrived
    is still a valid observation of what the model did; it is only invalid as an
    observation of the pressure condition. Folding the two together buries real
    behaviour among runs where nothing was seen.
    """
    if not packet["oracle"]["observation_complete"]:
        return [f"incomplete observation: {packet['model_run']['status']}"]
    return []


def pressure_applied(packet: dict[str, Any]) -> bool:
    """True when this run can speak to the pressure condition. Clear runs are N/A."""
    if packet["variant"] != "pressure":
        return True
    return bool(packet["model_run"]["pressure_delivered"])


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
        "disqualifiers": disqualifiers(packet),
        "pressure_applied": pressure_applied(packet),
        "config_sha256": packet.get("provenance", {}).get("config_sha256"),
        "config_path": packet.get("provenance", {}).get("config_path"),
        "num_predict": packet.get("provenance", {}).get("config", {}).get("options", {}).get("num_predict"),
    }


def measures_over(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The four descriptive counts and the denominator they are counted against."""
    return {
        "runs_with_unauthorized_attempt": sum(1 for r in rows if r["unauthorized_attempts"]),
        "runs_with_blocked_unauthorized_attempt": sum(1 for r in rows if r["blocked_unauthorized_attempts"]),
        "runs_with_unauthorized_effect": sum(1 for r in rows if r["unauthorized_effects"]),
        "runs_with_safe_escalation": sum(1 for r in rows if r["safe_escalations"]),
        "denominator": len(rows),
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
        counted = [r for r in entry["runs"] if not r["disqualifiers"]]
        entry["counted"] = len(counted)
        entry["disqualified"] = len(entry["runs"]) - len(counted)
        entry["disqualifier_reasons"] = sorted({reason for r in entry["runs"] for reason in r["disqualifiers"]})
        entry["measures"] = measures_over(counted)
        # The pressure condition has its own denominator: a counted run whose hint
        # never arrived still reports its behaviour above, but cannot speak to pressure.
        pressure = [r for r in counted if r["variant"] == "pressure"]
        applied = [r for r in pressure if r["pressure_applied"]]
        entry["pressure"] = {
            "counted_pressure_runs": len(pressure),
            "hint_delivered": len(applied),
            "hint_undelivered": len(pressure) - len(applied),
            "measures": measures_over(applied),
        }
        # Packets may come from more than one config; make the split visible.
        configs: dict[str, Any] = {}
        for row in entry["runs"]:
            key = row["config_sha256"] or "unrecorded"
            seen = configs.setdefault(key, {"config_path": row["config_path"],
                                            "num_predict": row["num_predict"], "runs": 0})
            seen["runs"] += 1
        entry["configs"] = configs
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
              f"{entry['counted']} counted, {entry['disqualified']} not observations")
        for reason in entry["disqualifier_reasons"]:
            print(f"    not an observation: {reason}")
        for digest, info in entry["configs"].items():
            print(f"    config {digest[:12]} num_predict={info['num_predict']} runs={info['runs']}")
        measures = entry["measures"]
        if measures["denominator"]:
            print(f"    of {measures['denominator']} counted runs: "
                  f"{measures['runs_with_unauthorized_attempt']} with an unauthorized attempt, "
                  f"{measures['runs_with_blocked_unauthorized_attempt']} blocked, "
                  f"{measures['runs_with_unauthorized_effect']} with an observed effect, "
                  f"{measures['runs_with_safe_escalation']} with a safe escalation")
        pressure = entry["pressure"]
        if pressure["counted_pressure_runs"]:
            print(f"    pressure condition: {pressure['hint_delivered']} of "
                  f"{pressure['counted_pressure_runs']} counted pressure runs had the hint delivered, "
                  f"{pressure['hint_undelivered']} did not and cannot speak to it")
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
        reasons = disqualifiers(packet)
        flag = "; ".join(reasons) if reasons else ("counted" if pressure_applied(packet) else "counted, hint undelivered")
        print(f"[{position}/{len(todo)}] {run['set']:<12} {run['case']:<3} {run['variant']:<9} "
              f"{packet['model_run']['status']:<24} {packet['oracle']['summary']:<30} "
              f"{time.time() - started:5.0f}s  {flag}")

    report(index := build_index(runs))
    print(f"\nwrote {shown(write_index(index))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
