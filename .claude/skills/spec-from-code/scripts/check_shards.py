#!/usr/bin/env python3
"""Gate G1: every in-scope source file (or every line of it, for files split into
line ranges) belongs to exactly one module.

Usage: check_shards.py --inventory specs/_meta/inventory.json --modules specs/_meta/modules.json
                       [--max-loc 6000] [--min-loc 150] [--out specs/_meta/shards-report.json]
Exit 1 on unassigned, multiply-assigned, gapped or overlapping ranges, over-limit modules,
or malformed modules.json.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import build_ownership, eprint, in_scope, read_json, scope_label, write_json

RESERVED = {"IF", "DATA", "CFG", "OPS", "SYS"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--modules", required=True)
    ap.add_argument("--max-loc", type=int, default=6000)
    ap.add_argument("--min-loc", type=int, default=150)
    ap.add_argument("--out", default=None, help="write report json here")
    args = ap.parse_args()
    inv = read_json(Path(args.inventory))
    repo = Path(inv["summary"]["repo_root"])
    mods = read_json(Path(args.modules))
    errors: list[str] = []
    warnings: list[str] = []

    modules = mods.get("modules", [])
    if not modules:
        errors.append("modules.json has no modules")
    ids, prefixes = set(), set()
    for m in modules:
        for k in ("id", "prefix", "name", "globs"):
            if k not in m:
                errors.append(f"module {m.get('id', '?')} missing field '{k}'")
        mid = m.get("id", "")
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", mid):
            errors.append(f"module id '{mid}' must be a lowercase slug")
        if mid in ids:
            errors.append(f"duplicate module id {mid}")
        ids.add(mid)
        pf = m.get("prefix", "")
        if not re.match(r"^[A-Z][A-Z0-9]{1,11}$", pf):
            errors.append(f"module {mid} prefix '{pf}' must be 2-12 uppercase alphanumerics")
        if pf in prefixes or pf in RESERVED:
            errors.append(f"module {mid} prefix '{pf}' duplicates another module or a reserved prefix {sorted(RESERVED)}")
        prefixes.add(pf)
        for dep in m.get("depends_on", []):
            if dep not in {x.get("id") for x in modules}:
                warnings.append(f"module {mid} depends_on unknown module '{dep}' (fine if it is out of scope; say so in survey.md)")
    for e in mods.get("excluded", []):
        if not e.get("reason"):
            warnings.append(f"excluded glob '{e.get('glob')}' has no reason")

    own = build_ownership(mods, inv["files"], repo)
    errors += own["range_errors"]
    in_scope_files = [f for f in inv["files"] if in_scope(f)]
    per_mod = {}
    for mid, items in own["assign"].items():
        loc = sum(i["loc"] for i in items)
        per_mod[mid] = {"files": len(items), "loc": loc, "paths": [scope_label(i) for i in items]}
        if not items:
            errors.append(f"module {mid} matches no in-scope files")
        elif loc > args.max_loc:
            errors.append(f"module {mid} has {loc} LOC > {args.max_loc}: split it (use split_file.py for single "
                          f"files over the limit) so one extractor can hold it")
        elif loc < args.min_loc:
            warnings.append(f"module {mid} has only {loc} LOC: consider merging")
    if own["unassigned"]:
        errors.append(f"{len(own['unassigned'])} in-scope source files are not assigned to any module")
    if own["multi"]:
        errors.append(f"{len(own['multi'])} files are assigned to more than one module")

    report = {
        "errors": errors, "warnings": warnings, "unassigned": own["unassigned"], "multiply_assigned": own["multi"],
        "excluded_files": len(own["excluded"]), "in_scope_files": len(in_scope_files),
        "modules": {k: {"files": v["files"], "loc": v["loc"]} for k, v in per_mod.items()},
        "module_paths": {k: v["paths"] for k, v in per_mod.items()},
    }
    if args.out:
        write_json(Path(args.out), report)
    for w in warnings:
        eprint("WARN:", w)
    for e in errors[:100]:
        eprint("ERROR:", e)
    for p in own["unassigned"][:50]:
        eprint("  unassigned:", p)
    for m in own["multi"][:50]:
        eprint("  multiple:", m["path"], "->", ", ".join(m["modules"]))
    eprint(f"shards: {len(modules)} modules, {len(in_scope_files)} in-scope files, {len(own['unassigned'])} unassigned, "
           f"{len(own['multi'])} multiply assigned, {len(own['range_errors'])} range errors, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
