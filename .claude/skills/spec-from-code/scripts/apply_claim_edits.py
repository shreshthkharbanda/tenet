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
    edited_ids: set[str] = set()
    edits_by_file: dict[str, list[dict]] = {}
    tail_counts: dict[str, int] = {}
    for df in sorted(rdir.glob("decisions-*.jsonl")):
        for d in read_jsonl(df):
            counts[d.get("verdict")] = counts.get(d.get("verdict"), 0) + 1
            row = overlaps[d["row"]] if 0 <= d.get("row", -1) < len(overlaps) else {}
            if row.get("tail_sample"):
                tail_counts[d.get("verdict")] = tail_counts.get(d.get("verdict"), 0) + 1
            for e in d.get("edits", []) or []:
                edits_by_file.setdefault(e["file"], []).append(e)
            if d.get("verdict") == "unresolvable":
                row = overlaps[d["row"]] if 0 <= d.get("row", -1) < len(overlaps) else {}
                questions.append(f"- [{row.get('a', {}).get('id', '?')}] vs [{row.get('b', {}).get('id', '?')}]: "
                                  f"{d.get('question', '')} Evidence: {d.get('evidence', '')}")
    # Conflicts: parallel judges may edit the same claim with different text. Applying in file order would
    # silently let the last one win, so conflicting claims are left untouched and listed for resolution.
    conflicts = []
    for rel in list(edits_by_file):
        groups: dict[str, list[dict]] = {}
        for e in edits_by_file[rel]:
            groups.setdefault(e["id"], []).append(e)
        keep = []
        for cid, es in groups.items():
            variants = {(e["text"].strip(), e.get("confidence"), tuple(e.get("refs") or ())) for e in es}
            if len(variants) > 1:
                conflicts.append({"file": rel, "id": cid, "variants": [e["text"] for e in es]})
            else:
                keep.append(es[0])
        edits_by_file[rel] = keep
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
            # A claim's block is its line plus continuation lines indented deeper than its bullet (wrapped
            # text, sub-bullets). Replace the whole block, or stale sub-bullets survive the edit.
            lead = len(m.group("lead")) - len(m.group("lead").lstrip())
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip() or LINE.match(nxt.rstrip("\n")) or nxt.lstrip().startswith(("#", "|")):
                    break
                if len(nxt) - len(nxt.lstrip()) <= lead:
                    break
                j += 1
            lines[i:j] = [f"{m.group('lead')}[{e['id']}] {{{conf}}} {ref_txt}{e['text'].strip()}\n"]
            index = {k: (v if v <= i else v - (j - i - 1)) for k, v in index.items()}
            edited_ids.add(e["id"])
            applied += 1
        if not a.dry_run:
            fp.write_text("".join(lines), encoding="utf-8")
    if questions and not a.dry_run:
        qf = specs / "_meta" / "questions.md"
        prev = qf.read_text() if qf.exists() else "# Open questions\n\nPairs of claims about the same code that the code itself does not settle.\n\n"
        qf.write_text(prev + "\n".join(questions) + "\n")
    # Pointer chains: a pointer whose target is itself a pointer makes the reader hop twice; flag them.
    POINTER = re.compile(r"\b(?:is|are) in \[([A-Z][A-Z0-9]{1,11}-\d{3,4})\]|see \[([A-Z][A-Z0-9]{1,11}-\d{3,4})\]|in \[([A-Z][A-Z0-9]{1,11}-\d{3,4})\]\.?$")
    texts = {}
    for fp in list(specs.glob("modules/*.md")) + list(specs.glob("0*.md")):
        for ln in fp.read_text(encoding="utf-8").splitlines():
            m = LINE.match(ln)
            if m:
                texts[m.group("id")] = m.group("rest")
    chains = []
    for cid, rest in texts.items():
        pm = POINTER.search(rest)
        tgt = next((g for g in pm.groups() if g), None) if pm else None
        if tgt and tgt in texts and POINTER.search(texts[tgt]):
            chains.append(f"{cid} -> {tgt} -> ...")
    # Tables repeat claim values in cells the applier cannot edit by ID; list rows that mention an edited
    # claim so they are re-checked by hand (or by the Reconciler).
    tables_to_review = []
    for fp in list(specs.glob("modules/*.md")) + list(specs.glob("0*.md")):
        for n, ln in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
            if ln.lstrip().startswith("|"):
                hit = sorted(set(re.findall(r"[A-Z][A-Z0-9]{1,11}-\d{3,4}", ln)) & edited_ids)
                if hit:
                    tables_to_review.append(f"{fp.relative_to(specs).as_posix()}:{n} ({', '.join(hit)})")
    if conflicts:
        write_json(rdir / "conflicts.json", conflicts)
    write_json(rdir / "applied.json", {"verdicts": counts, "edits_applied": applied, "errors": errors,
                                       "questions": len(questions), "conflicts": len(conflicts),
                                       "tail_sample_verdicts": tail_counts, "tables_to_review": tables_to_review,
                                       "pointer_chains": chains})
    if tail_counts:
        n = sum(tail_counts.values())
        bad = tail_counts.get("contradiction", 0) + tail_counts.get("unresolvable", 0)
        eprint(f"tail sample: {bad}/{n} contradictions or unresolvable below the cut"
               + (" -- the unjudged tail still hides contradictions: raise find_overlaps.py --max and judge more"
                  if n and bad / n >= 0.03 else ""))
    for c in conflicts:
        eprint(f"CONFLICT: {c['file']} {c['id']}: {len(c['variants'])} different edits; left unchanged, see reconcile/conflicts.json")
    for ch in chains[:20]:
        eprint("POINTER CHAIN:", ch)
    if tables_to_review:
        eprint(f"{len(tables_to_review)} table rows mention edited claims; re-check them (applied.json tables_to_review)")
    for e in errors:
        eprint("ERROR:", e)
    eprint(f"reconcile: verdicts {counts}; {applied} claim edits applied; {len(questions)} questions; {len(errors)} errors")
    return 1 if errors or conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
