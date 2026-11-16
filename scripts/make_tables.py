#!/usr/bin/env python3
"""Emit the manuscript's tables as markdown, computed from the packets on disk.

Numbers in the paper are generated, never typed. Run after collecting an arm:

  python3 scripts/make_tables.py            # writes paper/tables.md
  python3 scripts/make_tables.py --stdout   # prints instead

Every count is reported against an explicit denominator, and sets are never pooled.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agent_safety_pilot import load_cases  # noqa: E402

import run_pilot  # noqa: E402

SETS = ["primary", "determinism", "enforced"]

# Ways a run can fail to be an observation, and what each would have been recorded as
# by a harness that treated an empty trace as compliance.
FAILURE_MODES = {
    "truncated": "response hit the output cap before emitting a tool call",
    "unparsed_tool_call_text": "tool call written in prose instead of the tool channel",
    "transport_error": "model server failed or timed out",
    "turn_limit": "turn budget reached with the run unfinished",
    "tool_limit": "tool-call budget reached with calls discarded",
}

MEASURE_LABELS = [
    ("runs_with_unauthorized_attempt", "Runs with an unauthorized attempt"),
    ("runs_with_blocked_unauthorized_attempt", "Runs with a blocked unauthorized attempt"),
    ("runs_with_unauthorized_effect", "Runs with an observed unauthorized effect"),
    ("runs_with_safe_escalation", "Runs with a safe escalation"),
]


def table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_No runs collected._\n"
    line = "| " + " | ".join(headers) + " |"
    rule = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([line, rule, *body]) + "\n"


def collected(index: dict[str, Any]) -> dict[str, Any]:
    return {name: entry for name, entry in index["sets"].items() if entry["present"]}


def accounting(index: dict[str, Any]) -> str:
    rows = []
    for name in SETS:
        entry = index["sets"].get(name)
        if entry is None:
            continue
        reasons = "; ".join(entry["disqualifier_reasons"]) or "none"
        rows.append([name, entry["planned"], entry["present"], entry["counted"],
                     entry["disqualified"], reasons])
    return table(["Set", "Planned", "Attempted", "Counted observations",
                  "Not observations", "Why not"], rows)


def measures(index: dict[str, Any]) -> str:
    out = []
    for name, entry in collected(index).items():
        rows = [[label, entry["measures"][key], entry["measures"]["denominator"]]
                for key, label in MEASURE_LABELS]
        out.append(f"**{name}**, over counted runs\n\n" + table(["Measure", "Runs", "Denominator"], rows))
        pressure = entry["pressure"]
        if pressure["counted_pressure_runs"]:
            rows = [[label, pressure["measures"][key], pressure["measures"]["denominator"]]
                    for key, label in MEASURE_LABELS]
            out.append(
                f"**{name}**, pressure condition only. The hint reached the model in "
                f"{pressure['hint_delivered']} of {pressure['counted_pressure_runs']} counted "
                f"pressure runs; the remaining {pressure['hint_undelivered']} cannot speak to it.\n\n"
                + table(["Measure", "Runs", "Denominator"], rows))
    return "\n".join(out)


def per_run(index: dict[str, Any]) -> str:
    out = []
    for name, entry in collected(index).items():
        rows = []
        for row in sorted(entry["runs"], key=lambda r: (r["case"], r["variant"])):
            rows.append([
                row["case"], row["variant"], row["status"], row["summary"],
                "yes" if not row["disqualifiers"] else "no",
                "n/a" if row["variant"] != "pressure" else ("yes" if row["pressure_applied"] else "no"),
                row["num_predict"] or "unrecorded",
            ])
        out.append(f"**{name}**\n\n" + table(
            ["Case", "Variant", "Run status", "Oracle summary", "Counted",
             "Hint delivered", "num_predict"], rows))
    return "\n".join(out)


def demonstrations() -> dict[str, str]:
    """Deliberately provoked packets, keyed by the status they evidence."""
    found = {}
    for path in sorted((ROOT / "results" / "demonstrations").glob("*.json")):
        packet = json.loads(path.read_text())
        if not packet.get("demonstration", {}).get("not_pilot_data"):
            continue
        found[packet["model_run"]["status"]] = str(path.relative_to(ROOT))
    return found


def failures(index: dict[str, Any]) -> str:
    seen: dict[str, int] = {}
    for entry in collected(index).values():
        for row in entry["runs"]:
            if row["disqualifiers"]:
                seen[row["status"]] = seen.get(row["status"], 0) + 1
    demos = demonstrations()
    rows = []
    for status, description in FAILURE_MODES.items():
        rows.append([status, description, seen.get(status, 0), demos.get(status, "none")])
    return table(["Status", "What happened", "Runs in the pilot", "Demonstration packet"], rows)


def provenance(index: dict[str, Any]) -> str:
    rows = []
    for name, entry in collected(index).items():
        for digest, info in entry["configs"].items():
            rows.append([name, info["config_path"] or "unrecorded", digest[:12],
                         info["num_predict"] or "unrecorded", info["runs"]])
    return table(["Set", "Config", "sha256", "num_predict", "Runs"], rows)


def identity(index: dict[str, Any]) -> str:
    """Model, revision and case version, read from the first packet that records them."""
    for entry in collected(index).values():
        for row in entry["runs"]:
            path = ROOT / row["output"]
            if not path.exists():
                continue
            packet = json.loads(path.read_text())
            p = packet.get("provenance", {})
            if not p.get("model"):
                continue
            revision = p.get("git_revision", {})
            rows = [
                ["Model", p.get("model", "unrecorded")],
                ["Model digest", p.get("model_digest", "unrecorded")],
                ["Model capabilities", ", ".join(p.get("model_capabilities", [])) or "unrecorded"],
                ["Case set version", packet.get("case_version", "unrecorded")],
                ["Evidence packet schema", packet.get("schema_version", "unrecorded")],
                ["Sandbox version", packet.get("environment", {}).get("sandbox_version", "unrecorded")],
                ["Repository revision", revision.get("value", "unrecorded") if isinstance(revision, dict) else revision],
                ["Working tree clean at run time", "no" if p.get("git_dirty") else "yes"],
            ]
            return table(["Field", "Value"], rows)
    return "_No packet records provenance._\n"


def build() -> str:
    cases = load_cases()
    runs = run_pilot.planned_runs(cases, SETS)
    index = run_pilot.build_index(runs)
    parts = [
        "# Generated tables",
        "",
        f"Generated {index['generated']} by `scripts/make_tables.py` from the packets in `results/`.",
        "Do not edit by hand. Counts are observations, not rates, and no set is pooled with another.",
        "",
        "## Table 1. Run accounting",
        "",
        accounting(index),
        "## Table 2. Descriptive measures",
        "",
        measures(index),
        "## Table 3. Every run",
        "",
        per_run(index),
        "## Table 4. Observation failures",
        "",
        "A run that is not a complete observation is excluded from the measures above. "
        "Each status below is a way a harness that treated an empty trace as compliance "
        "would instead have recorded the run as clean. Where a status did not arise in the "
        "pilot, a deliberately provoked packet evidences it; those packets are marked as "
        "demonstrations and are never counted as observations of model behaviour.",
        "",
        failures(index),
        "## Table 5. Run configuration",
        "",
        provenance(index),
        "## Table 6. Study identity",
        "",
        identity(index),
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stdout", action="store_true", help="print instead of writing paper/tables.md")
    args = parser.parse_args()
    text = build()
    if args.stdout:
        print(text)
        return 0
    out = ROOT / "paper" / "tables.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text if text.endswith("\n") else text + "\n")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
