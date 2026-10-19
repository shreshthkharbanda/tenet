#!/usr/bin/env python3
"""Gate G1: every in-scope source file belongs to exactly one module.

Usage: check_shards.py --inventory specs/_meta/inventory.json --modules specs/_meta/modules.json [--max-loc 6000]
Exit 1 on unassigned or multiply-assigned files, or malformed modules.json.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import ID_RE, eprint, glob_to_regex, read_json, write_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--modules", required=True)
    ap.add_argument("--max-loc", type=int, default=6000)
    ap.add_argument("--min-loc", type=int, default=150)
    ap.add_argument("--out", default=None, help="write report json here")
    args = ap.parse_args()
    inv = read_json(Path(args.inventory))
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
            errors.append(f"module id '{mid}' must be lowercase slug")
        if mid in ids:
            errors.append(f"duplicate module id {mid}")
        ids.add(mid)
        pf = m.get("prefix", "")
        if not re.match(r"^[A-Z][A-Z0-9]{1,11}$", pf):
            errors.append(f"module {mid} prefix '{pf}' must be 2-12 uppercase alnum chars")
        if pf in prefixes or pf in {"IF", "DATA", "CFG", "OPS", "SYS"}:
            errors.append(f"module {mid} prefix '{pf}' duplicates another module or a reserved cross-cutting prefix")
        prefixes.add(pf)

    excluded = [(e.get("glob", ""), e.get("reason", "")) for e in mods.get("excluded", [])]
    ex_rx = [(glob_to_regex(g), g, r) for g, r in excluded if g]
    mod_rx = [(m, [glob_to_regex(g) for g in m.get("globs", [])]) for m in modules]

    in_scope = [f for f in inv["files"] if f["kind"] == "source" and not f["is_test"] and not f["is_generated"]]
    unassigned, multi = [], []
    per_mod = {m["id"]: {"files": 0, "loc": 0, "paths": []} for m in modules if "id" in m}
    excluded_files = []
    for f in in_scope:
        p = f["path"]
        if any(rx.match(p) for rx, _, _ in ex_rx):
            excluded_files.append(p)
            continue
        owners = [m["id"] for m, rxs in mod_rx if any(rx.match(p) for rx in rxs)]
        if not owners:
            unassigned.append(p)
        elif len(owners) > 1:
            multi.append({"path": p, "modules": owners})
        else:
            per_mod[owners[0]]["files"] += 1
            per_mod[owners[0]]["loc"] += f["loc"]
            per_mod[owners[0]]["paths"].append(p)

    for mid, st in per_mod.items():
        if st["files"] == 0:
            errors.append(f"module {mid} matches no in-scope files")
        elif st["loc"] > args.max_loc:
            warnings.append(f"module {mid} has {st['loc']} LOC > {args.max_loc}: split it so one extractor can hold it")
        elif st["loc"] < args.min_loc:
            warnings.append(f"module {mid} has only {st['loc']} LOC: consider merging")
    if unassigned:
        errors.append(f"{len(unassigned)} in-scope source files are not assigned to any module")
    if multi:
        errors.append(f"{len(multi)} files are assigned to more than one module")
    for g, r in excluded:
        if not r:
            warnings.append(f"excluded glob '{g}' has no reason")

    report = {
        "errors": errors, "warnings": warnings, "unassigned": unassigned, "multiply_assigned": multi,
        "excluded_files": len(excluded_files),
        "modules": {k: {"files": v["files"], "loc": v["loc"]} for k, v in per_mod.items()},
    }
    if args.out:
        write_json(Path(args.out), report | {"module_paths": {k: v["paths"] for k, v in per_mod.items()}})
    for w in warnings:
        eprint("WARN:", w)
    for e in errors:
        eprint("ERROR:", e)
    for p in unassigned[:50]:
        eprint("  unassigned:", p)
    for m in multi[:50]:
        eprint("  multiple:", m["path"], "->", ", ".join(m["modules"]))
    eprint(f"shards: {len(modules)} modules, {len(in_scope)} in-scope files, "
           f"{len(unassigned)} unassigned, {len(multi)} multiply assigned, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
