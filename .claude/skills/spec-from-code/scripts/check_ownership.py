#!/usr/bin/env python3
"""Gate G6: one fact, one owner. Measures restatement, the source of duplicate claims that drift apart.

Every in-scope line is owned by exactly one module (G1). A claim whose refs cite lines owned by module M
should live in M's spec, or point to M's claim with a cross-reference [M-NNN]. This gate counts:
  - restated: cross-cutting claims (01-04, 00) citing module-owned lines with no [ID] pointer to a
    claim of a module that owns those lines
  - foreign: module claims whose every line ref falls in another module's lines, with no [ID] pointer
    to a claim of that module
Pointer claims (containing [ID]) and claims citing only out-of-scope code are fine.

Usage: check_ownership.py <specs_dir> --repo <root> [--max-restated 0.2] [--max-foreign 0.1]
Exit 1 when a file exceeds its threshold. Writes _meta/ownership.json.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import XREF_RE, build_ownership, eprint, parse_claims, parse_frontmatter, read_json, write_json

LINE_REF = re.compile(r"^(.+?):L?(\d+)(?:-L?(\d+))?$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--max-restated", type=float, default=0.2)
    ap.add_argument("--max-foreign", type=float, default=0.1)
    a = ap.parse_args()
    specs, repo = Path(a.specs).resolve(), Path(a.repo).resolve()
    inv = read_json(specs / "_meta" / "inventory.json")
    mods = read_json(specs / "_meta" / "modules.json")
    own = build_ownership(mods, inv["files"], repo)
    owner_spans: dict[str, list[tuple[int, int, str]]] = {}
    for mid, items in own["assign"].items():
        for it in items:
            owner_spans.setdefault(it["path"], []).append((it["start"], it["end"], mid))

    def owners(ref: str) -> set[str]:
        m = LINE_REF.match(ref.strip())
        path = m.group(1) if m else ref.split("::")[0]
        spans = owner_spans.get(path, [])
        if not m:
            return {s[2] for s in spans} if len(spans) == 1 else set()
        lo, hi = int(m.group(2)), int(m.group(3) or m.group(2))
        return {mid for a_, b_, mid in spans if not (hi < a_ or lo > b_)}

    # which module's spec defines each claim ID: a pointer counts only if it names a claim of a module
    # that owns the cited lines (a pointer to another cross-cutting claim, or to an unrelated module, is
    # not a hand-off to the owner)
    id_module: dict[str, str] = {}
    for fp in sorted(specs.glob("modules/*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        for c in parse_claims(body):
            id_module[c["id"]] = fm.get("module")

    report, fails = {}, []
    for fp in sorted(specs.glob("modules/*.md")) + sorted(specs.glob("0*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        rel = fp.relative_to(specs).as_posix()
        mine = fm.get("module")
        claims = [c for c in parse_claims(body) if c["section"] not in ("Open questions and gaps", "Suspected defects")]
        flagged = []
        for c in claims:
            os_ = set()
            for r in c["refs"]:
                os_ |= owners(r)
            if not os_:
                continue  # cites only out-of-scope code: nobody else owns it
            if any(id_module.get(x) in os_ - {mine} for x in XREF_RE.findall(c["text"])):
                continue  # points to a claim of a module that owns the cited lines
            if mine is None and os_:
                flagged.append(c["id"])  # cross-cutting restating module-owned behavior
            elif mine is not None and mine not in os_:
                flagged.append(c["id"])  # module claim entirely about another module's lines
        n = len(claims)
        rate = len(flagged) / n if n else 0.0
        limit = a.max_restated if mine is None else a.max_foreign
        ok = rate <= limit
        report[rel] = {"claims": n, "flagged": len(flagged), "rate": round(rate, 3), "limit": limit, "ok": ok,
                       "kind": "restated" if mine is None else "foreign", "ids": flagged[:200]}
        if not ok:
            fails.append(rel)
    write_json(specs / "_meta" / "ownership.json", report)
    for rel, r in report.items():
        if not r["ok"]:
            eprint(f"OWNERSHIP: {rel}: {r['flagged']}/{r['claims']} claims {r['kind']} without a pointer "
                   f"({r['rate']:.0%} > {r['limit']:.0%}); point to the owning module's claim ID instead of restating")
    eprint(f"ownership: {len(report)} spec files, {len(fails)} over threshold -> _meta/ownership.json")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
