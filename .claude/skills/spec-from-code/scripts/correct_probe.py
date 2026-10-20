#!/usr/bin/env python3
"""Correct a probe whose reference answer a judge showed (with evidence) to be wrong, once, on the record.

A wrong reference mis-scores the probe in every later round, so leaving it is worse than fixing it. The
correction never changes the question or the split, and is logged to _meta/probe-corrections.jsonl with
the reason and evidence, so held-out integrity is auditable: the fix is about the code, not the spec.

Usage: correct_probe.py <specs_dir> --id PROBE_ID (--append TEXT | --replace TEXT) --reason TEXT --evidence TEXT
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from _common import eprint, read_jsonl, write_jsonl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--id", required=True)
    g = ap.add_mutually_exclusive_group(required=False)
    g.add_argument("--append")
    g.add_argument("--replace")
    ap.add_argument("--question-append", default=None,
                    help="sharpen an ambiguous question (e.g. pin a setup detail); never changes its split")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--evidence", required=True)
    a = ap.parse_args()
    meta = Path(a.specs).resolve() / "_meta"
    hit = None
    for pf in sorted((meta / "probes").glob("*.jsonl")):
        rows = read_jsonl(pf)
        for r in rows:
            if r["id"] == a.id:
                old = r["reference_answer"]
                if a.replace is not None:
                    r["reference_answer"] = a.replace
                elif a.append is not None:
                    r["reference_answer"] = old.rstrip() + " " + a.append.strip()
                if a.question_append:
                    r["question"] = r["question"].rstrip() + " " + a.question_append.strip()
                r["corrected"] = r.get("corrected", 0) + 1
                hit = (pf, old, r["reference_answer"])
        if hit and hit[0] == pf:
            write_jsonl(pf, rows)
            break
    if not hit:
        raise SystemExit(f"no probe {a.id}")
    if a.append is None and a.replace is None and not a.question_append:
        raise SystemExit("nothing to correct: pass --append, --replace, or --question-append")
    with open(meta / "probe-corrections.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": a.id, "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "reason": a.reason,
                            "evidence": a.evidence, "old": hit[1], "new": hit[2]}) + "\n")
    eprint(f"corrected {a.id} in {hit[0].name}; logged to _meta/probe-corrections.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
