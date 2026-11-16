#!/usr/bin/env python3
"""Draw the two figures the methods note needs, as SVG, with no new dependencies.

  python3 scripts/make_figures.py          # writes paper/figures/*.svg
  python3 scripts/make_figures.py --png    # also rasterizes, if a converter is installed

Figure 1 is the decision path from a model response to a run label, marking where each
observation failure sits and the path a harness without the guard takes instead.
Figure 2 is the A2 run as an outcome reviewer and a trace reviewer would each see it.

Figure 2 reads its content from the packet rather than from prose, so it cannot drift
from the data. If the packet is absent the figure is skipped rather than invented.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "paper" / "figures"
A2 = ROOT / "results" / "primary" / "A2-pressure.json"

INK = "#1b1b1b"
MUTED = "#6b6b6b"
GOOD = "#1f6f43"
BAD = "#9c2c2c"
LINE = "#9a9a9a"
FONT = "Helvetica, Arial, sans-serif"
MONO = "ui-monospace, Menlo, Consolas, monospace"


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def box(x, y, w, h, label, sub="", *, stroke=INK, fill="#ffffff", dash=False, anchor_size=13):
    dashes = ' stroke-dasharray="5 4"' if dash else ""
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.5"{dashes}/>'
    ]
    cy = y + h / 2 + (0 if not sub else -7)
    parts.append(
        f'<text x="{x + w / 2}" y="{cy}" text-anchor="middle" font-family="{FONT}" '
        f'font-size="{anchor_size}" fill="{INK}" dominant-baseline="middle">{esc(label)}</text>'
    )
    if sub:
        parts.append(
            f'<text x="{x + w / 2}" y="{cy + 16}" text-anchor="middle" font-family="{MONO}" '
            f'font-size="11" fill="{MUTED}" dominant-baseline="middle">{esc(sub)}</text>'
        )
    return "".join(parts)


def arrow(x1, y1, x2, y2, label="", *, colour=LINE, dash=False, label_dx=6, label_dy=-5):
    dashes = ' stroke-dasharray="5 4"' if dash else ""
    out = [
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
        f'stroke-width="1.5" marker-end="url(#arrow)"{dashes}/>'
    ]
    if label:
        out.append(
            f'<text x="{(x1 + x2) / 2 + label_dx}" y="{(y1 + y2) / 2 + label_dy}" '
            f'font-family="{FONT}" font-size="11" fill="{MUTED}">{esc(label)}</text>'
        )
    return "".join(out)


def text(x, y, body, *, size=12, colour=INK, font=FONT, anchor="start", weight="normal"):
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" fill="{colour}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{esc(body)}</text>')


def svg(width, height, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">'
        f'<title>{esc(title)}</title>'
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{LINE}"/>'
        '</marker></defs>'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
        f'{body}</svg>\n'
    )


def figure_one() -> str:
    b = []
    b.append(text(30, 34, "From a model response to a run label", size=16, weight="600"))
    b.append(text(30, 54, "Only one path produces an observation. The dashed path is what a harness "
                          "without the guard does instead.", size=12, colour=MUTED))

    b.append(box(40, 80, 180, 44, "Model response"))
    b.append(arrow(130, 124, 130, 156))
    b.append(box(40, 156, 180, 48, "Structured tool calls?", ""))
    b.append(arrow(220, 180, 300, 180, "yes"))
    b.append(box(300, 156, 190, 48, "Execute, log, continue", ""))
    b.append(arrow(395, 156, 395, 110))
    b.append(arrow(395, 110, 230, 110, "next turn"))

    b.append(arrow(130, 204, 130, 236, "no"))
    b.append(box(40, 236, 180, 48, "Output cap reached?"))
    b.append(arrow(220, 260, 300, 260, "yes"))
    b.append(box(300, 236, 230, 48, "truncated", "not an observation", stroke=BAD))

    b.append(arrow(130, 284, 130, 316, "no"))
    b.append(box(40, 316, 180, 56, "Content parses as", "a tool call?"))
    b.append(arrow(220, 344, 300, 344, "yes"))
    b.append(box(300, 316, 230, 56, "unparsed_tool_call_text", "not an observation", stroke=BAD))

    b.append(arrow(130, 372, 130, 404, "no"))
    b.append(box(40, 404, 180, 48, "completed", "observation", stroke=GOOD))

    b.append(box(560, 156, 200, 48, "Server error or timeout", ""))
    b.append(arrow(660, 204, 660, 236))
    b.append(box(560, 236, 200, 48, "transport_error", "not an observation", stroke=BAD))

    b.append(box(560, 316, 200, 56, "Runner budget reached", ""))
    b.append(arrow(660, 372, 660, 404))
    b.append(box(560, 404, 200, 48, "turn_limit / tool_limit", "not an observation", stroke=BAD))

    # The path a harness without the guard takes: no calls, therefore clean.
    b.append(arrow(22, 180, 22, 478, "", colour=BAD, dash=True))
    b.append(arrow(22, 478, 300, 478, "", colour=BAD, dash=True))
    b.append(box(300, 456, 230, 44, "no boundary crossing", "scored as a clean pass",
                 stroke=BAD, dash=True))
    b.append(text(30, 522, "Without the guard: no recorded call is read as no attempted action.",
                  size=11, colour=BAD))

    return svg(800, 545, "".join(b), "Decision path from a model response to a run label")


def figure_two() -> str | None:
    if not A2.exists():
        return None
    packet = json.loads(A2.read_text())
    calls = [e for e in packet["trace"] if e["kind"] == "tool_call"]
    final = packet["outcome"]["final_response"]
    call = calls[0]["call"] if calls else {}
    authorized = calls[0]["authorized"] if calls else None
    result = calls[0]["result"] if calls else None

    def wrap(body, width=52):
        words, lines, line = str(body).split(), [], ""
        for word in words:
            if len(line) + len(word) + 1 > width:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            lines.append(line)
        return lines[:4]

    b = []
    b.append(text(30, 34, f"Case {packet['case_id']}, {packet['variant']} variant: two reviewers, "
                          "two conclusions", size=16, weight="600"))
    b.append(text(30, 54, "Both views are generated from the same packet.", size=12, colour=MUTED))

    b.append(f'<rect x="30" y="74" width="360" height="300" rx="8" fill="#fbfbfb" stroke="{LINE}"/>')
    b.append(text(46, 98, "Outcome view", size=13, weight="600"))
    b.append(text(46, 120, "request, final response, final state", size=11, colour=MUTED))
    b.append(text(46, 152, "Final response", size=11, colour=MUTED))
    for i, line in enumerate(wrap(final, 48)):
        b.append(text(46, 172 + i * 16, line, size=11, font=MONO))
    b.append(text(46, 300, "A reviewer sees a plausible summary", size=12))
    b.append(text(46, 318, "and a completed task.", size=12))
    b.append(text(46, 348, "verdict: pass", size=12, colour=BAD, weight="600"))

    b.append(f'<rect x="420" y="74" width="360" height="300" rx="8" fill="#fbfbfb" stroke="{LINE}"/>')
    b.append(text(436, 98, "Trace view", size=13, weight="600"))
    b.append(text(436, 120, "the same, plus every attempted call", size=11, colour=MUTED))
    b.append(text(436, 152, "Attempted call", size=11, colour=MUTED))
    b.append(text(436, 172, f"{call.get('action', '?')} {call.get('resource', '?')}", size=11, font=MONO))
    b.append(text(436, 192, f"authorized: {authorized}", size=11, font=MONO, colour=BAD))
    b.append(text(436, 212, f"result: {json.dumps(result)}", size=11, font=MONO))
    b.append(text(436, 244, "Then the same final response,", size=12))
    b.append(text(436, 262, "stating figures the call never returned.", size=12))
    b.append(text(436, 300, "A reviewer sees an out-of-scope read", size=12))
    b.append(text(436, 318, "that returned nothing, then invention.", size=12))
    b.append(text(436, 348, "verdict: contest", size=12, colour=GOOD, weight="600"))

    b.append(text(30, 402, "The outcome view withholds the trace, the checker's labels and the "
                           "adjudication block by construction.", size=11, colour=MUTED))
    return svg(810, 420, "".join(b), f"Case {packet['case_id']} outcome view versus trace view")


def rasterize(path: Path) -> str:
    png = path.with_suffix(".png")
    for tool, args in (
        ("rsvg-convert", ["-w", "1600", "-o", str(png), str(path)]),
        ("inkscape", [str(path), "--export-type=png", "-w", "1600", f"--export-filename={png}"]),
        ("convert", ["-density", "200", str(path), str(png)]),
    ):
        if shutil.which(tool):
            subprocess.run([tool, *args], check=True, capture_output=True)
            return f"{png.relative_to(ROOT)} via {tool}"
    try:
        import cairosvg
    except ImportError:
        return "no converter found: install librsvg2-bin, inkscape, imagemagick or cairosvg"
    cairosvg.svg2png(url=str(path), write_to=str(png), output_width=1600)
    return f"{png.relative_to(ROOT)} via cairosvg"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--png", action="store_true", help="also rasterize to PNG if a converter exists")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    figures = {"figure-1-decision-path.svg": figure_one(), "figure-2-two-views.svg": figure_two()}
    written = []
    for name, body in figures.items():
        if body is None:
            print(f"skipped {name}: {A2.relative_to(ROOT)} is not present, and the figure is "
                  "generated from it rather than written by hand", file=sys.stderr)
            continue
        path = OUT / name
        path.write_text(body)
        written.append(path)
        print(f"wrote {path.relative_to(ROOT)}")

    if args.png:
        for path in written:
            print(f"  {rasterize(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())