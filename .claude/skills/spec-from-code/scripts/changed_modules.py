#!/usr/bin/env python3
"""Update mode: list modules whose in-scope files changed between the commit recorded in
modules.json and HEAD, plus files that are new and unassigned.

Usage: changed_modules.py <specs_dir> --repo <root>
Prints JSON {"from": sha, "to": sha, "changed_modules": [...], "new_unassigned": [...], "deleted": [...]}.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from _common import eprint, git_head, glob_to_regex, read_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    repo = Path(args.repo).resolve()
    mods = read_json(specs / "_meta" / "modules.json")
    base = mods.get("commit")
    head = git_head(repo)
    if not base or not head:
        raise SystemExit("need modules.json commit and a git HEAD")
    if base == head:
        print(json.dumps({"from": base, "to": head, "changed_modules": [], "new_unassigned": [], "deleted": []}))
        return 0
    out = subprocess.run(["git", "-C", str(repo), "diff", "--name-status", f"{base}..{head}"],
                         capture_output=True, text=True, check=True).stdout
    changed, deleted, new = [], [], []
    for line in out.splitlines():
        parts = line.split("\t")
        status, path = parts[0][0], parts[-1]
        (deleted if status == "D" else new if status == "A" else changed).append(path)
    mod_rx = [(m["id"], [glob_to_regex(g) for g in m.get("globs", [])]) for m in mods.get("modules", [])]
    ex_rx = [glob_to_regex(e["glob"]) for e in mods.get("excluded", []) if e.get("glob")]
    touched, unassigned = set(), []
    for p in changed + new + deleted:
        if any(rx.match(p) for rx in ex_rx):
            continue
        owners = [mid for mid, rxs in mod_rx if any(rx.match(p) for rx in rxs)]
        touched.update(owners)
        if not owners and p in new and p.rsplit(".", 1)[-1] in {"py", "js", "ts", "tsx", "jsx", "java", "kt", "go", "rs", "rb", "php", "cs", "scala", "swift", "ex"}:
            unassigned.append(p)
    result = {"from": base, "to": head, "changed_modules": sorted(touched), "new_unassigned": unassigned, "deleted": deleted}
    print(json.dumps(result, indent=2))
    eprint(f"update: {len(touched)} modules touched, {len(unassigned)} new unassigned files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
