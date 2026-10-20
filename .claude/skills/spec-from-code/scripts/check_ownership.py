#!/usr/bin/env python3
"""Gate G6: one fact, one owner. Measures restatement, the source of duplicate claims that drift apart.

Every in-scope line is owned by exactly one module (G1). A claim whose refs cite lines owned by module M
should live in M's spec, or point to M's claim with a cross-reference [M-NNN]. This gate counts:
  - restated: cross-cutting claims (01-04, 00) citing module-owned lines with no [ID] pointer to a
    claim of a module that owns those lines
  - foreign: module claims whose every line ref falls in another module's lines, with no [ID] pointer
    to a claim of that module
A pointer counts only when the claim it names is RELATED to the pointing claim: it cites overlapping
lines of the same file, or shares a distinctive backticked literal. Appending the owning module's first
claim ID to every restatement passed under L56 (red team E9: 312 claims, 0 files over threshold);
honest pointers are related 98-100% of the time. A `::Symbol` ref resolves to the definition's lines
and a bare path into a file split across modules is owned by every module holding part of it, so
neither escapes as "out of scope". Claims citing only out-of-scope code are fine.

Usage: check_ownership.py <specs_dir> --repo <root> [--max-restated 0.2] [--max-foreign 0.1]
Exit 1 when a file exceeds its threshold. Writes _meta/ownership.json.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import (XREF_RE, build_ownership, eprint, parse_claims, parse_frontmatter, read_json, ref_path, ref_span,
                     write_json)

LIT = re.compile(r"`([^`\n]{3,80})`")
TRIVIAL = {"None", "True", "False", "null", "self", "str", "int", "dict", "list", "bool", "float", "model", "kwargs"}


def literals(text: str) -> set[str]:
    return {t.strip() for t in LIT.findall(text) if t.strip() not in TRIVIAL}


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
        sp = ref_span(repo, ref)
        if sp is None:  # bare path, or a symbol naming no definition: every module holding part of the file
            return {s[2] for s in owner_spans.get(ref_path(ref), [])}
        path, lo, hi = sp
        return {mid for a_, b_, mid in owner_spans.get(path, []) if not (hi < a_ or lo > b_)}

    def spans(c: dict) -> list[tuple[str, int, int]]:
        return [s for s in (ref_span(repo, r) for r in c["refs"]) if s]

    # which module's spec defines each claim ID: a pointer counts only if it names a claim of a module
    # that owns the cited lines (a pointer to another cross-cutting claim, or to an unrelated module, is
    # not a hand-off to the owner), and only if that claim is about the same thing
    id_module: dict[str, str] = {}
    id_claim: dict[str, dict] = {}
    for fp in sorted(specs.glob("modules/*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        for c in parse_claims(body):
            id_module[c["id"]] = fm.get("module")
            id_claim[c["id"]] = c

    def related(c: dict, target_id: str) -> bool:
        t = id_claim[target_id]
        if any(p == q and not (b1 < a2 or b2 < a1) for p, a1, b1 in spans(c) for q, a2, b2 in spans(t)):
            return True
        return bool(literals(c["text"]) & literals(t["text"]))

    report, fails = {}, []
    for fp in sorted(specs.glob("modules/*.md")) + sorted(specs.glob("0*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        rel = fp.relative_to(specs).as_posix()
        mine = fm.get("module")
        claims = [c for c in parse_claims(body) if c["section"] not in ("Open questions and gaps", "Suspected defects")]
        flagged = []
        to_owner = unrelated = 0
        for c in claims:
            os_ = set()
            for r in c["refs"]:
                os_ |= owners(r)
            if not os_:
                continue  # cites only out-of-scope code: nobody else owns it
            ptrs = [x for x in XREF_RE.findall(c["text"]) if id_module.get(x) in os_ - {mine}]
            if ptrs:
                to_owner += 1
                if any(related(c, x) for x in ptrs):
                    continue  # points to a related claim of a module that owns the cited lines
                unrelated += 1
            if mine is None and os_:
                flagged.append(c["id"])  # cross-cutting restating module-owned behavior
            elif mine is not None and mine not in os_:
                flagged.append(c["id"])  # module claim entirely about another module's lines
        n = len(claims)
        rate = len(flagged) / n if n else 0.0
        limit = a.max_restated if mine is None else a.max_foreign
        ok = rate <= limit
        report[rel] = {"claims": n, "flagged": len(flagged), "rate": round(rate, 3), "limit": limit, "ok": ok,
                       "kind": "restated" if mine is None else "foreign", "ids": flagged[:200],
                       "pointers_to_owner": to_owner, "pointers_unrelated": unrelated}
        if not ok:
            fails.append(rel)
    write_json(specs / "_meta" / "ownership.json", report)
    for rel, r in report.items():
        if not r["ok"]:
            eprint(f"OWNERSHIP: {rel}: {r['flagged']}/{r['claims']} claims {r['kind']} without a pointer "
                   f"({r['rate']:.0%} > {r['limit']:.0%}); point to the owning module's claim ID instead of restating"
                   + (f"; {r['pointers_unrelated']} pointer(s) name an owner's claim about something else (no shared "
                      f"lines or literal)" if r["pointers_unrelated"] else ""))
    eprint(f"ownership: {len(report)} spec files, {len(fails)} over threshold -> _meta/ownership.json")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
