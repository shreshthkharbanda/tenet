#!/usr/bin/env python3
"""Build the spec-only snapshot answerers read: a copy of specs/ with reference answers stripped
from probes (questions only) and all answers/judgments/revise material removed.

Usage: snapshot_for_answerers.py <specs_dir> --out <scratch>/spec-snapshot-round-N
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _common import eprint, read_jsonl, write_jsonl


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
    shutil.copytree(specs, out, ignore=shutil.ignore_patterns(
        "answers", "judgments", "revise", "rounds", "rebuild", "worker-reports", "briefs", "skill-refs", "audit", "survey.md", "env.md", "dispatch.jsonl", "queue.txt",
        "inventory.json", "shards-report.json", "coverage.json", "lint-report.json", "validation.json",
        "verify-report.json", "status.json", "traceability.md", "validation-report.md"))
    if args.questions_only:
        for f in list(out.rglob("*")):
            if f.is_file() and not (f.suffix == ".jsonl" and "probes" in f.parts):
                f.unlink()
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
