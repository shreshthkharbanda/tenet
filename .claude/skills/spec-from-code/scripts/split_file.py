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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("path")
    ap.add_argument("--max-loc", type=int, default=3500)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    fp = Path(args.repo) / args.path
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    n = len(lines)
    nb = [0] * (n + 1)
    for i, ln in enumerate(lines, 1):
        nb[i] = nb[i - 1] + (1 if ln.strip() else 0)
    b = [x for x in boundaries(lines) if x[0] > 1]
    cuts = [(1, "(file start)")] + b
    ranges, start, start_name = [], 1, "(file start)"
    last_name = start_name
    for k, (line, name) in enumerate(cuts[1:], 1):
        seg_loc = nb[line - 1] - nb[start - 1]
        if seg_loc >= args.max_loc and line > start:
            ranges.append({"start": start, "end": line - 1, "loc": seg_loc, "first": start_name, "last": last_name})
            start, start_name = line, name
        last_name = name
        # lookahead: if adding up to the next cut overflows, cut here
        nxt = cuts[k + 1][0] if k + 1 < len(cuts) else n + 1
        if nb[nxt - 1] - nb[start - 1] > args.max_loc and line > start:
            ranges.append({"start": start, "end": line - 1, "loc": nb[line - 1] - nb[start - 1], "first": start_name,
                           "last": cuts[k - 1][1]})
            start, start_name = line, name
    ranges.append({"start": start, "end": n, "loc": nb[n] - nb[start - 1], "first": start_name, "last": last_name})
    warnings = [f"segment {r['start']}-{r['end']} has {r['loc']} LOC > {args.max_loc}: a single definition is larger "
                f"than the limit; give it its own module and tell the extractor to read it in ranges" for r in ranges
                if r["loc"] > args.max_loc]
    if args.json:
        print(json.dumps({"path": args.path, "lines": n, "ranges": ranges, "warnings": warnings}, indent=2))
    else:
        for r in ranges:
            print(f'"{args.path}:{r["start"]}-{r["end"]}"   # {r["loc"]} LOC, {r["first"]} .. {r["last"]}')
        for w in warnings:
            print("WARN:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
