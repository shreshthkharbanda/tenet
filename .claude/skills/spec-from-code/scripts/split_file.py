#!/usr/bin/env python3
"""Propose line-range cut points for a source file too large for one extractor.

Cuts only at definition boundaries: top-level definitions, or member definitions directly
inside a top-level class-like block (never inside a function). Leading decorators and
comments stay with the definition they annotate. Greedy-packs consecutive segments up to
--max-loc non-blank lines.

Usage: split_file.py <repo_root> <path> [--max-loc 3500] [--json]
Prints ranges as module-ready entries ("path:START-END") with the first and last
definition in each, so the Surveyor can name modules by responsibility.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEF_RE = re.compile(r"^(?P<ind>[ \t]*)(?:@|(?:async\s+)?def\s|class\s|func\s|fn\s|pub(?:\([^)]*\))?\s|public\s|private\s|"
                    r"protected\s|internal\s|static\s|export\s|function\s|interface\s|type\s|impl\s|module\s|"
                    r"object\s|trait\s|enum\s|struct\s|abstract\s|override\s|suspend\s|fun\s)")
CLASS_LIKE = re.compile(r"^(?:export\s+)?(?:public\s+|abstract\s+|final\s+|sealed\s+|data\s+)*"
                        r"(?:class|interface|object|impl|struct|enum|trait|module)\b")
NAME_RE = re.compile(r"(?:def|class|func|fn|function|interface|type|struct|enum|trait|object|fun)\s+([A-Za-z_]\w*)")


def boundaries(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line, name) for each allowed cut point."""
    out = []
    top_kind = "other"
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        ind = len(ln) - len(ln.lstrip())
        stripped = ln.strip()
        if ind == 0 and not stripped.startswith(("#", "//", "@", "*", "/*")):
            top_kind = "class" if CLASS_LIKE.match(stripped) else "other"
        m = DEF_RE.match(ln)
        if not m:
            continue
        ok = ind == 0 or (ind <= 4 and top_kind == "class")
        if not ok:
            continue
        # walk up over decorators / comments at the same indentation with no blank line between
        j = i
        while j > 0:
            prev = lines[j - 1]
            ps = prev.strip()
            pind = len(prev) - len(prev.lstrip())
            if ps and pind == ind and (ps.startswith(("@", "#", "//", "/*", "*")) or ps.endswith("*/")):
                j -= 1
            else:
                break
        if stripped.startswith("@"):
            continue  # the def below will claim this decorator line
        nm = NAME_RE.search(ln)
        out.append((j + 1, nm.group(1) if nm else stripped[:40]))
    # dedupe by line, keep order
    seen, res = set(), []
    for ln_no, name in out:
        if ln_no not in seen:
            seen.add(ln_no)
            res.append((ln_no, name))
    return res


def name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"_+|(?<=[a-z])(?=[A-Z])", name) if t]


def cohesion_penalty(lines: list[str], cuts: list[tuple[int, str]], k: int) -> int:
    """Cost of cutting before cuts[k]: shared name prefix between the definitions on either side
    (e.g. _inherit_builtin_a | _inherit_builtin_b) plus calls crossing the cut between the three
    definitions on each side. Lower is better."""
    before = [c[1] for c in cuts[max(0, k - 3):k]]
    after = [c[1] for c in cuts[k:k + 3]]
    a, b = name_tokens(before[-1]) if before else [], name_tokens(after[0]) if after else []
    shared = 0
    for x, y in zip(a, b):
        if x != y:
            break
        shared += 1
    lo = cuts[max(0, k - 3)][0]
    mid = cuts[k][0]
    hi = cuts[k + 3][0] if k + 3 < len(cuts) else len(lines) + 1
    left, right = "\n".join(lines[lo - 1:mid - 1]), "\n".join(lines[mid - 1:hi - 1])
    crossing = sum(len(re.findall(r"\b" + re.escape(n) + r"\s*\(", right)) for n in before) + \
        sum(len(re.findall(r"\b" + re.escape(n) + r"\s*\(", left)) for n in after)
    return 3 * shared + crossing


def cost_note(r: dict) -> str:
    return f" (cut cost {r['cut_penalty']})" if r.get("cut_penalty") else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("path")
    ap.add_argument("--max-loc", type=int, default=3500)
    ap.add_argument("--window", type=float, default=0.7,
                    help="consider cut points once a chunk reaches this fraction of --max-loc, and pick the most "
                         "cohesive one (fewest calls across, least shared name prefix) before the cap")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    fp = Path(args.repo) / args.path
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    n = len(lines)
    nb = [0] * (n + 1)
    for i, ln in enumerate(lines, 1):
        nb[i] = nb[i - 1] + (1 if ln.strip() else 0)
    cuts = [(1, "(file start)")] + [x for x in boundaries(lines) if x[0] > 1]
    ranges, start_k = [], 0
    while True:
        start = cuts[start_k][0]
        if nb[n] - nb[start - 1] <= args.max_loc:
            break
        cands = [k for k in range(start_k + 1, len(cuts))
                 if args.window * args.max_loc <= nb[cuts[k][0] - 1] - nb[start - 1] <= args.max_loc]
        if not cands:  # no boundary in the window: take the last one under the cap, or the first one at all
            under = [k for k in range(start_k + 1, len(cuts)) if nb[cuts[k][0] - 1] - nb[start - 1] <= args.max_loc]
            cands = [under[-1]] if under else ([start_k + 1] if start_k + 1 < len(cuts) else [])
        if not cands:
            break
        best = min(cands, key=lambda k: (cohesion_penalty(lines, cuts, k), -k))
        end = cuts[best][0] - 1
        ranges.append({"start": start, "end": end, "loc": nb[end] - nb[start - 1], "first": cuts[start_k][1],
                       "last": cuts[best - 1][1], "cut_penalty": cohesion_penalty(lines, cuts, best)})
        start_k = best
    start = cuts[start_k][0]
    ranges.append({"start": start, "end": n, "loc": nb[n] - nb[start - 1], "first": cuts[start_k][1],
                   "last": cuts[-1][1], "cut_penalty": 0})
    warnings = [f"segment {r['start']}-{r['end']} has {r['loc']} LOC > {args.max_loc}: a single definition is larger "
                f"than the limit; give it its own module and tell the extractor to read it in ranges" for r in ranges
                if r["loc"] > args.max_loc]
    if args.json:
        print(json.dumps({"path": args.path, "lines": n, "ranges": ranges, "warnings": warnings,
                          "boundaries": [c[0] for c in cuts]}, indent=2))
    else:
        for r in ranges:
            print(f'"{args.path}:{r["start"]}-{r["end"]}"   # {r["loc"]} LOC, {r["first"]} .. {r["last"]}'
                  f'{cost_note(r)}')
        for w in warnings:
            print("WARN:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
