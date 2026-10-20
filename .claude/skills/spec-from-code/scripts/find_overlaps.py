#!/usr/bin/env python3
"""Candidate contradictions for the Reconciler: pairs of claims from DIFFERENT spec files whose refs
cite overlapping lines of the same file. Two descriptions of the same code are where independently
written specs disagree; reading thousands of claims for contradictions is hopeless, checking a few
hundred pairs is not. Pairs whose texts share a distinctive literal with different values nearby are
ranked first.

Usage: find_overlaps.py <specs_dir> [--max 400] -> _meta/overlaps.jsonl
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import eprint, parse_claims, parse_frontmatter, write_jsonl

LINE_REF = re.compile(r"^(.+?):L?(\d+)(?:-L?(\d+))?$")
NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def jaccard(x: str, y: str) -> float:
    a, b = set(w.lower() for w in WORD.findall(x)), set(w.lower() for w in WORD.findall(y))
    return len(a & b) / len(a | b) if a | b else 0.0
LIT = re.compile(r"`([^`]{2,60})`")


def spans(refs: list[str]) -> list[tuple[str, int, int]]:
    out = []
    for r in refs:
        m = LINE_REF.match(r.strip())
        if m:
            a = int(m.group(2))
            out.append((m.group(1), a, int(m.group(3) or a)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--max", type=int, default=400)
    ap.add_argument("--max-span", type=int, default=120, help="ignore refs wider than this many lines (too coarse to pair)")
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    claims = []
    for fp in sorted(specs.glob("modules/*.md")) + sorted(specs.glob("0*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        for c in parse_claims(body):
            sp = [s for s in spans(c["refs"]) if s[2] - s[1] <= a.max_span]
            if sp:
                claims.append((fp.relative_to(specs).as_posix(), c, sp))
    by_path: dict[str, list[int]] = {}
    for i, (_, _, sp) in enumerate(claims):
        for p, _, _ in sp:
            by_path.setdefault(p, []).append(i)
    pairs, seen = [], set()
    for p, idx in by_path.items():
        idx = sorted(set(idx))
        for x in range(len(idx)):
            for y in range(x + 1, len(idx)):
                i, j = idx[x], idx[y]
                if claims[i][0] == claims[j][0] or (i, j) in seen:
                    continue
                si = [s for s in claims[i][2] if s[0] == p]
                sj = [s for s in claims[j][2] if s[0] == p]
                if not any(not (b1 < a2 or b2 < a1) for _, a1, b1 in si for _, a2, b2 in sj):
                    continue
                seen.add((i, j))
                ti, tj = claims[i][1]["text"], claims[j][1]["text"]
                ni, nj = set(NUM.findall(ti)), set(NUM.findall(tj))
                li, lj = set(LIT.findall(ti)), set(LIT.findall(tj))
                # suspicion: shared literals (same subject) with differing numbers or literals (different value)
                score = len(li & lj) * 2 + (3 if (ni and nj and ni != nj) else 0) + (2 if (li ^ lj) and (li & lj) else 0)
                sim = jaccard(ti, tj)
                kind = "duplicate" if sim >= 0.45 else "same-code"
                pairs.append({"score": score, "similarity": round(sim, 3), "kind": kind, "path": p,
                              "a": {"file": claims[i][0], "id": claims[i][1]["id"], "refs": claims[i][1]["refs"], "text": ti},
                              "b": {"file": claims[j][0], "id": claims[j][1]["id"], "refs": claims[j][1]["refs"], "text": tj}})
    pairs.sort(key=lambda r: -r["score"])
    dups = [r for r in pairs if r["kind"] == "duplicate"]
    # duplicates whose values differ are the likeliest real contradictions; then other suspicious pairs
    dup_conflict = [r for r in dups if r["score"] >= 3]
    rest = [r for r in pairs if r not in dup_conflict]
    write_jsonl(specs / "_meta" / "overlaps.jsonl", (dup_conflict + rest)[: a.max])
    files_dup: dict[str, int] = {}
    for r in dups:
        for side in ("a", "b"):
            files_dup[r[side]["file"]] = files_dup.get(r[side]["file"], 0) + 1
    eprint(f"overlaps: {len(pairs)} cross-file pairs on shared lines; {len(dups)} near-duplicates "
           f"({len(dup_conflict)} with differing values); top {min(len(pairs), a.max)} -> _meta/overlaps.jsonl")
    eprint("near-duplicate involvement by file: " + ", ".join(f"{k} {v}" for k, v in sorted(files_dup.items(), key=lambda kv: -kv[1])[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
