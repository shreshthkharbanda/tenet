#!/usr/bin/env python3
"""Write a worker report with the one schema verify_reports.py checks. Workers call this instead of
hand-writing JSON, because hand-written reports drift (LiteLLM iteration 1: judges invented "worker",
"inputs", "spec_files_read" keys and the gate could verify nothing).

Usage:
  write_report.py --specs DIR --role ROLE --module ID [--round N] [--snapshot DIR]
                  [--output PATH[:CLAIMS]] ... [--read PATH] ... [--read-from FILE]
                  [--note TEXT] [--bug "WHERE|WHAT|EVIDENCE"] ...
--read-from takes a file with one path per line (handy for long read lists).
Writes <specs>/_meta/worker-reports/<role>-<module>[-round-N].json and prints its path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROLES = {"surveyor", "extractor", "interfaces", "data", "config", "operations", "crosscut", "reconciler", "pairjudge",
         "prober", "answerer", "judge", "reviser", "rebuilder", "falsifier", "omission", "control", "judge-auditor",
         "redteam", "reader", "lifecycle-checker"}


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
        p = str(Path(path).resolve())
        outputs.append({"path": p, "claims": int(n)} if n else {"path": p})
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
    out = Path(a.specs).resolve() / "_meta" / "worker-reports" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
