#!/usr/bin/env python3
"""Merge every defect source for a module into one reviser input:
  _meta/revise/round-N/<module>.jsonl (already holds revision-split probe failures, answer_notes,
  defect_notes from score_probes.py) plus
  - falsifier rows (audit/falsify-<module>.jsonl, and universal-pass files) with verdict false/imprecise
  - omission rows (audit/omission-<module>.jsonl) with spec_status vague/missing/contradicted
  - lint warnings on the module's spec (placeholder rendering, untracked table values)
  - rebuild guesses and spec bugs (rebuild/<module>.json)
None of these carries held-out probe content, so they are safe to give the writer.
Usage: build_revise.py <specs_dir> --repo <root> --round N
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from _common import eprint, read_json, read_jsonl, write_jsonl

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--round", type=int, required=True)
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    meta = specs / "_meta"
    out_dir = meta / "revise" / f"round-{a.round}"
    out_dir.mkdir(parents=True, exist_ok=True)
    mods = [m["id"] for m in read_json(meta / "modules.json")["modules"]]
    lint = subprocess.run([sys.executable, str(HERE / "lint_specs.py"), str(specs), "--repo", a.repo],
                          capture_output=True, text=True).stderr.splitlines()
    totals = {}
    for mid in mods:
        f = out_dir / f"{mid}.jsonl"
        rows = read_jsonl(f) if f.exists() else []
        seen = {(r.get("source"), r.get("id")) for r in rows}
        add = []
        for ff in sorted((meta / "audit").glob(f"falsify-{mid}*.jsonl")) + sorted((meta / "audit").glob(f"universal-falsify-{mid}*.jsonl")):
            for r in read_jsonl(ff):
                if r.get("verdict") in ("false", "imprecise", "ref_wrong") and ("falsifier", r["id"]) not in seen:
                    add.append({"source": "falsifier", "id": r["id"], "verdict": r["verdict"], "severity": r.get("severity"),
                                "judge_note": r.get("evidence", ""), "counterexample": r.get("counterexample", "")})
        of = meta / "audit" / f"omission-{mid}.jsonl"
        if of.exists():
            for r in read_jsonl(of):
                if r.get("spec_status") in ("vague", "missing", "contradicted"):
                    key = ("omission", f"rank-{r.get('rank')}")
                    if key not in seen:
                        add.append({"source": "omission", "id": f"rank-{r.get('rank')}", "verdict": r["spec_status"],
                                    "question": r.get("behavior"), "refs": r.get("refs", []),
                                    "judge_note": r.get("note", ""), "spec_claims": r.get("spec_claims", [])})
        for ln in lint:
            if f"modules/{mid}.md:" in ln and ln.startswith("WARN"):
                m = re.search(r"modules/[\w-]+\.md:(\d+): (.*)", ln)
                if m and ("lint", m.group(1)) not in seen:
                    add.append({"source": "lint", "id": m.group(1), "verdict": "warning", "judge_note": m.group(2)})
        rb = meta / "rebuild" / f"{mid}.json"
        if rb.exists():
            r = read_json(rb)
            for i, g in enumerate(r.get("guesses", [])):
                add.append({"source": "rebuild", "id": f"guess-{i}", "verdict": "guess", "judge_note": json.dumps(g)})
            for i, b in enumerate(r.get("spec_bugs", [])):
                add.append({"source": "rebuild", "id": f"spec-bug-{i}", "verdict": "spec_bug", "judge_note": str(b)})
        for r in rows:
            if "source" not in r:
                r["source"] = r["verdict"] if r.get("verdict") in ("answer_note", "defect_note") else "probe"
        # idempotent: re-running after a brief or skill fix must not duplicate rows (L58: rebuild rows were
        # appended twice and a reviser worked 68 rows of which 27 were repeats)
        merged, keys = [], set()
        for r in rows + add:
            k = (r.get("source"), str(r.get("id")))
            if k not in keys:
                keys.add(k)
                merged.append(r)
        write_jsonl(f, merged)
        totals[mid] = {}
        for r in merged:
            totals[mid][r["source"]] = totals[mid].get(r["source"], 0) + 1
    for mid, t in totals.items():
        eprint(f"{mid}: " + ", ".join(f"{k} {v}" for k, v in sorted(t.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
