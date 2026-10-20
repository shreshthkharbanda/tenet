#!/usr/bin/env python3
"""Write a worker report with the one schema verify_reports.py checks. Workers call this instead of
hand-writing JSON, because hand-written reports drift (LiteLLM iteration 1: judges invented "worker",
"inputs", "spec_files_read" keys and the gate could verify nothing).

Usage:
  write_report.py --specs DIR --role ROLE --module ID [--round N] [--snapshot DIR]
                  [--output PATH[:CLAIMS]] ... [--read PATH] ... [--read-from FILE]
                  [--note TEXT] [--bug "WHERE|WHAT|EVIDENCE"] ...
--read-from takes a file with one path per line (handy for long read lists).
Writes <role>-<module>[-round-N].json under <specs>/_meta/worker-reports/ (eval roles: under the eval
dir's worker-reports/) and prints its path. Claim counts and sha256 of each output are computed here,
not taken from the worker (L57): a count the worker states is kept as claims_reported for comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from _common import EVAL_ROLES, eval_dir, parse_claims, parse_frontmatter

ROLES = {"surveyor", "extractor", "interfaces", "data", "config", "operations", "crosscut", "reconciler", "pairjudge",
         "prober", "answerer", "judge", "reviser", "rebuilder", "falsifier", "omission", "control", "judge-auditor",
         "redteam", "reader", "lifecycle-checker", "verifier", "narrator", "system-narrator", "story-judge", "story-reader", "story-scorer", "persona-reader", "teachback-judge"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True)
    ap.add_argument("--role", required=True, choices=sorted(ROLES))
    ap.add_argument("--module", required=True)
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--output", action="append", default=[])
    ap.add_argument("--read", action="append", default=[])
    ap.add_argument("--read-from", default=None)
    ap.add_argument("--note", action="append", default=[])
    ap.add_argument("--bug", action="append", default=[])
    a = ap.parse_args()
    outputs = []
    for o in a.output:
        path, _, n = o.rpartition(":") if o.rsplit(":", 1)[-1].isdigit() else (o, "", "")
        fp = Path(path).resolve()
        rec = {"path": str(fp)}
        if n:
            rec["claims_reported"] = int(n)
        if fp.is_file():
            data = fp.read_bytes()
            rec["sha256"] = hashlib.sha256(data).hexdigest()
            rec["mtime"] = fp.stat().st_mtime
            if fp.suffix == ".md":
                rec["claims"] = len(parse_claims(parse_frontmatter(data.decode("utf-8", "replace"))[1]))
        outputs.append(rec)
    reads = [str(Path(r).resolve()) for r in a.read]
    if a.read_from:
        reads += [str(Path(l.strip()).resolve()) for l in Path(a.read_from).read_text().splitlines() if l.strip()]
    bugs = []
    for b in a.bug:
        parts = [x.strip() for x in b.split("|")]
        if len(parts) < 2:
            raise SystemExit(f"--bug expects 'WHERE|WHAT|EVIDENCE', got {b!r}")
        bugs.append({"where": parts[0], "what": parts[1], "evidence": parts[2] if len(parts) > 2 else ""})
    rep = {"role": a.role, "module": a.module, "outputs": outputs, "files_read": sorted(set(reads)),
           "notes": " ".join(a.note), "suspected_bugs": bugs}
    if a.round is not None:
        rep["round"] = a.round
    if a.snapshot:
        rep["snapshot"] = str(Path(a.snapshot).resolve())
    name = f"{a.role}-{a.module}" + (f"-round-{a.round}" if a.round is not None else "") + ".json"
    base = eval_dir(Path(a.specs)) if a.role in EVAL_ROLES else Path(a.specs).resolve() / "_meta"
    out = base / "worker-reports" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
