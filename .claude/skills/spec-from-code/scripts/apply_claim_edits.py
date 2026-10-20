#!/usr/bin/env python3
"""Apply pair-judge decisions to spec files mechanically: each edit rewrites one claim line, found by
ID, keeping the ID. Parallel judges never touch spec files, so there are no edit races; this script
is the only writer. Unresolvable pairs are appended to _meta/questions.md.

Usage: apply_claim_edits.py <specs_dir> [--dry-run]
Reads every _meta/reconcile/decisions-*.jsonl. Exit 1 if any edit names a claim that does not exist.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _common import eprint, read_jsonl, write_json

LINE = re.compile(r"^(?P<lead>\s*[-*]\s+)\[(?P<id>[A-Z][A-Z0-9]{1,11}-\d{3,4})\]\s+\{(?P<conf>confirmed|inferred|gap)\}\s*(?P<rest>.*)$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    rdir = specs / "_meta" / "reconcile"
    overlaps = [json.loads(l) for l in (specs / "_meta" / "overlaps.jsonl").read_text().splitlines() if l.strip()]
    from _common import split_refs
    errors, applied, counts, questions = [], 0, {}, []
    edits_by_file: dict[str, list[dict]] = {}
    for df in sorted(rdir.glob("decisions-*.jsonl")):
        for d in read_jsonl(df):
            counts[d.get("verdict")] = counts.get(d.get("verdict"), 0) + 1
            for e in d.get("edits", []) or []:
                edits_by_file.setdefault(e["file"], []).append(e)
            if d.get("verdict") == "unresolvable":
                row = overlaps[d["row"]] if 0 <= d.get("row", -1) < len(overlaps) else {}
                questions.append(f"- [{row.get('a', {}).get('id', '?')}] vs [{row.get('b', {}).get('id', '?')}]: "
                                  f"{d.get('question', '')} Evidence: {d.get('evidence', '')}")
    for rel, edits in edits_by_file.items():
        fp = specs / rel
        if not fp.exists():
            errors.append(f"edit targets missing file {rel}")
            continue
        lines = fp.read_text(encoding="utf-8").splitlines(keepends=True)
        index = {}
        for i, ln in enumerate(lines):
            m = LINE.match(ln.rstrip("\n"))
            if m:
                index[m.group("id")] = i
        for e in edits:
            i = index.get(e["id"])
            if i is None:
                errors.append(f"{rel}: no claim {e['id']} to edit")
                continue
            m = LINE.match(lines[i].rstrip("\n"))
            old_refs, _ = split_refs(m.group("rest"))
            refs = e.get("refs") or old_refs
            conf = e.get("confidence") or m.group("conf")
            ref_txt = (", ".join(f"`{r}`" for r in refs) + " ") if refs else ""
            lines[i] = f"{m.group('lead')}[{e['id']}] {{{conf}}} {ref_txt}{e['text'].strip()}\n"
            applied += 1
        if not a.dry_run:
            fp.write_text("".join(lines), encoding="utf-8")
    if questions and not a.dry_run:
        qf = specs / "_meta" / "questions.md"
        prev = qf.read_text() if qf.exists() else "# Open questions\n\nPairs of claims about the same code that the code itself does not settle.\n\n"
        qf.write_text(prev + "\n".join(questions) + "\n")
    write_json(rdir / "applied.json", {"verdicts": counts, "edits_applied": applied, "errors": errors,
                                       "questions": len(questions)})
    for e in errors:
        eprint("ERROR:", e)
    eprint(f"reconcile: verdicts {counts}; {applied} claim edits applied; {len(questions)} questions; {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
