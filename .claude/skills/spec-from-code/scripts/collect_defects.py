#!/usr/bin/env python3
"""Collect suspected defects from every spec's "## Suspected defects" section and from worker
reports ("suspected_bugs": [...]) into _meta/suspected-defects.md, for the human review.

Usage: collect_defects.py <specs_dir>
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _common import eprint, parse_claims, parse_frontmatter


def spans(where: str) -> list[tuple[str, int, int]]:
    out = []
    for ref in re.findall(r"[\w./-]+\.\w+:\d+(?:-\d+)?", where or ""):
        path, rng = ref.rsplit(":", 1)
        a, _, b = rng.partition("-")
        out.append((path, int(a), int(b or a)))
    return out


def overlaps(x: list, y: list) -> bool:
    return any(p == q and not (b1 < a2 or b2 < a1) for p, a1, b1 in x for q, a2, b2 in y)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    rows = []
    for fp in sorted(specs.glob("modules/*.md")) + sorted(specs.glob("0*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        for c in parse_claims(body):
            if c["section"] == "Suspected defects":
                rows.append((fm.get("module") or fm.get("kind"), c["id"], ", ".join(c["refs"]), c["text"]))
    for rf in sorted((specs / "_meta" / "worker-reports").glob("*.json")):
        try:
            r = json.loads(rf.read_text())
        except Exception:
            continue
        for b in r.get("suspected_bugs", []) or []:
            if isinstance(b, dict):
                rows.append((r.get("module", "?"), f"({r.get('role')})", b.get("where", ""), b.get("what", "") + (" Evidence: " + b["evidence"] if b.get("evidence") else "")))
    # Convergence: the same code flagged by independent workers (different modules or roles) is the strongest
    # signal a defect is real. Count, for each row, how many OTHER sources point at overlapping lines.
    sp = [spans(w) for _, _, w, _ in rows]
    conv = []
    for i, (m, _, _, _) in enumerate(rows):
        others = {rows[j][0] + rows[j][1] for j in range(len(rows)) if j != i and rows[j][0] != m and overlaps(sp[i], sp[j])}
        conv.append(len(others))
    order = sorted(range(len(rows)), key=lambda i: -conv[i])
    lines = ["# Suspected defects", "", "Behavior the code exhibits that looks unintended. The specs state what the code does; "
             "this list says where that looks wrong. Each needs a decision: fix the code, or accept and keep the spec. "
             "Independent sources counts other modules or roles that flagged overlapping lines; two or more independent "
             "sources is strong evidence.", "",
             "| Module | Claim | Where | Independent sources | What and why |", "|---|---|---|---:|---|"]
    lines += [f"| {rows[i][0]} | {rows[i][1]} | `{rows[i][2]}` | {conv[i]} | {rows[i][3]} |" for i in order]
    (specs / "_meta" / "suspected-defects.md").write_text("\n".join(lines) + "\n")
    eprint(f"collected {len(rows)} suspected defects -> _meta/suspected-defects.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
