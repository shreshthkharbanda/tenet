#!/usr/bin/env python3
"""Collect suspected defects from every spec's "## Suspected defects" section and from worker
reports ("suspected_bugs": [...]) into _meta/suspected-defects.md, for the human review.

Usage: collect_defects.py <specs_dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import eprint, parse_claims, parse_frontmatter


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
    lines = ["# Suspected defects", "", "Behavior the code exhibits that looks unintended. The specs state what the code does; "
             "this list says where that looks wrong. Each needs a decision: fix the code, or accept and keep the spec.", "",
             "| Module | Claim | Where | What and why |", "|---|---|---|---|"]
    lines += [f"| {m} | {i} | `{w}` | {t} |" for m, i, w, t in rows]
    (specs / "_meta" / "suspected-defects.md").write_text("\n".join(lines) + "\n")
    eprint(f"collected {len(rows)} suspected defects -> _meta/suspected-defects.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
