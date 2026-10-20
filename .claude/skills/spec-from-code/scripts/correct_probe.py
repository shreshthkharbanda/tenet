#!/usr/bin/env python3
"""Correct a probe whose reference answer a judge showed (with evidence) to be wrong, once, on the record.

A wrong reference mis-scores the probe in every later round, so leaving it is worse than fixing it. The
correction never changes the split, and is logged to <eval>/probe-corrections.jsonl with the reason,
the evidence, and the old and new reference AND question, so held-out integrity is auditable: the fix is
about the code, not the spec. --evidence must cite code that resolves (path:START-END or path::Symbol).
A held-out probe needs --allow-holdout: it is the score's ground truth, and every such edit is listed in
the human report (L57).

Usage: correct_probe.py <specs_dir> --id PROBE_ID (--append TEXT | --replace TEXT | --question-append TEXT)
                        --reason TEXT --evidence "path:START-END ..." [--allow-holdout]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from _common import REF_RE, eprint, eval_dir, read_json, read_jsonl, resolve_ref, write_jsonl


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
    ap.add_argument("--allow-holdout", action="store_true")
    a = ap.parse_args()
    if a.append is None and a.replace is None and not a.question_append:
        raise SystemExit("nothing to correct: pass --append, --replace, or --question-append")
    specs = Path(a.specs).resolve()
    ev = eval_dir(specs)
    run = specs / "_meta" / "run.json"
    repo = Path(read_json(run)["repo"]) if run.exists() and read_json(run).get("repo") else (
        Path(read_json(specs / "_meta" / "inventory.json")["summary"]["repo_root"]))
    cands = REF_RE.findall(a.evidence) + a.evidence.split()
    if not any(resolve_ref(repo, c.strip("`,;()"))[0] for c in cands if (":" in c and "/" in c)):
        raise SystemExit("--evidence must cite code that resolves, e.g. `litellm/router.py:120-140`")
    hit = None
    for pf in sorted(p for p in (ev / "probes").glob("*.jsonl") if not p.name.endswith(".questions.jsonl")):
        rows = read_jsonl(pf)
        for r in rows:
            if r["id"] == a.id:
                if r.get("split") == "holdout" and not a.allow_holdout:
                    raise SystemExit(f"{a.id} is held out; pass --allow-holdout if the reference is provably wrong")
                old, old_q = r["reference_answer"], r["question"]
                if a.replace is not None:
                    r["reference_answer"] = a.replace
                elif a.append is not None:
                    r["reference_answer"] = old.rstrip() + " " + a.append.strip()
                if a.question_append:
                    r["question"] = r["question"].rstrip() + " " + a.question_append.strip()
                r["corrected"] = r.get("corrected", 0) + 1
                hit = (pf, old, r["reference_answer"], old_q, r["question"], r.get("split"))
        if hit and hit[0] == pf:
            write_jsonl(pf, rows)
            break
    if not hit:
        raise SystemExit(f"no probe {a.id}")
    with open(ev / "probe-corrections.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": a.id, "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "reason": a.reason,
                            "evidence": a.evidence, "split": hit[5], "old": hit[1], "new": hit[2],
                            "old_question": hit[3], "new_question": hit[4]}) + "\n")
    eprint(f"corrected {a.id} in {hit[0].name}; logged to {ev}/probe-corrections.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
