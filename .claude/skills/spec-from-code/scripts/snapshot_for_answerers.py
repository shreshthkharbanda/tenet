#!/usr/bin/env python3
"""Build the spec-only snapshot answerers read: spec text (allowlist), the module map, and the probe
questions from the eval dir with reference answers stripped.

Usage: snapshot_for_answerers.py <specs_dir> --out <scratch>/spec-snapshot-round-N
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _common import eprint, eval_dir, read_jsonl, write_jsonl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--questions-only", action="store_true",
                    help="no-spec control: the snapshot holds question files only, no spec text at all")
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    out = Path(args.out).resolve()
    repo_guess = specs.parent
    try:
        out.relative_to(repo_guess)
        if (repo_guess / ".git").exists():
            raise SystemExit(f"snapshot {out} is inside the repository {repo_guess}; put it in the scratch dir")
    except ValueError:
        pass
    if out.exists():
        shutil.rmtree(out)
    # ALLOWLIST, never a denylist: spec text, the module map, and questions. A denylist leaked every new
    # _meta file added later (probe corrections carry reference answers; reconcile decisions carry code
    # evidence), which is how answerers would learn what the spec does not say.
    out.mkdir(parents=True)
    keep = [specs / "INDEX.md"] + sorted(specs.glob("0*.md")) + sorted((specs / "modules").glob("*.md"))
    if not args.questions_only:
        for f in keep:
            if f.exists():
                dst = out / f.relative_to(specs)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
        (out / "_meta").mkdir(exist_ok=True)
        if (specs / "_meta" / "modules.json").exists():
            shutil.copy2(specs / "_meta" / "modules.json", out / "_meta" / "modules.json")
    (out / "_meta" / "probes").mkdir(parents=True, exist_ok=True)
    for pf in sorted((eval_dir(specs) / "probes").glob("*.jsonl")):
        if not pf.name.endswith(".questions.jsonl"):
            shutil.copy2(pf, out / "_meta" / "probes" / pf.name)
    pdir = out / "_meta" / "probes"
    n = 0
    if pdir.exists():
        for pf in sorted(pdir.glob("*.jsonl")):
            rows = read_jsonl(pf)
            write_jsonl(pf.with_suffix(".questions.jsonl"), [{"id": r["id"], "question": r["question"]} for r in rows])
            pf.unlink()
            n += len(rows)
    if args.questions_only and pdir.exists():
        for f in pdir.glob("*.questions.jsonl"):
            f.rename(out / f.name)
        for d in sorted((x for x in out.rglob("*") if x.is_dir()), reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass
    eprint(f"snapshot: {out} ({n} questions, no reference answers, no source)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
