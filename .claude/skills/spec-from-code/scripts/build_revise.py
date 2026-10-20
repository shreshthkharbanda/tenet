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
    prefix = {m["id"]: m.get("prefix") for m in read_json(meta / "modules.json")["modules"]}
    lint = subprocess.run([sys.executable, str(HERE / "lint_specs.py"), str(specs), "--repo", a.repo],
                          capture_output=True, text=True).stderr.splitlines()
    totals = {}
    for mid in mods:
        f = out_dir / f"{mid}.jsonl"
        rows = read_jsonl(f) if f.exists() else []
        def key(r: dict, default_round=None) -> tuple:
            # audit findings are keyed by the audit round that produced them: a claim found wrong again in a
            # later audit is a new finding, and omission ranks restart every round
            return (r.get("source"), str(r.get("id")), r.get("audit_round", default_round))
        seen = {key(r) for r in rows}
        # one-time findings (rebuild guesses, notes) were handed to an earlier round's reviser: never again
        # (L61: 27 already-fixed rebuild rows came back in round 2). Probe, lint and audit rows recur only
        # while they still fail, because their sources are re-measured each round.
        earlier = set()
        for k in range(1, a.round):
            pf = meta / "revise" / f"round-{k}" / f"{mid}.jsonl"
            if pf.exists():
                earlier |= {key(r, k if r.get("source") in ("falsifier", "omission") else None) for r in read_jsonl(pf)
                            if r.get("source") in ("rebuild", "note", "falsifier", "omission")}
        add = []
        # every audit round up to this one: an audit run after the last revision (an experiment, a fresh
        # sample) feeds the next revision; rows already handed out are skipped below (L66)
        audit_dirs = [(k, meta / "audit" / f"round-{k}") for k in range(1, a.round + 2)]
        for k, d in audit_dirs:
            for ff in sorted(d.glob(f"falsify-{mid}*.jsonl")) + sorted(d.glob(f"universal-falsify-{mid}*.jsonl")):
                for r in read_jsonl(ff):
                    row = {"source": "falsifier", "id": r["id"], "audit_round": k, "verdict": r["verdict"],
                           "severity": r.get("severity"), "judge_note": r.get("evidence", ""),
                           "counterexample": r.get("counterexample", "")}
                    if r.get("verdict") in ("false", "imprecise", "ref_wrong") and key(row) not in seen:
                        seen.add(key(row))
                        add.append(row)
            of = d / f"omission-{mid}.jsonl"
            for r in (read_jsonl(of) if of.exists() else []):
                row = {"source": "omission", "id": f"rank-{r.get('rank')}", "audit_round": k, "verdict": r.get("spec_status"),
                       "question": r.get("behavior"), "refs": r.get("refs", []), "judge_note": r.get("note", ""),
                       "spec_claims": r.get("spec_claims", [])}
                if r.get("spec_status") in ("vague", "missing", "contradicted") and key(row) not in seen:
                    seen.add(key(row))
                    add.append(row)
        for ln in lint:
            if f"modules/{mid}.md:" in ln and ln.startswith("WARN"):
                m = re.search(r"modules/[\w-]+\.md:(\d+): (.*)", ln)
                if m and ("lint", m.group(1)) not in seen:
                    add.append({"source": "lint", "id": m.group(1), "verdict": "warning", "judge_note": m.group(2)})
        # "module claim X-NNN: problem" notes from any worker (cross-cutting writers, falsifiers, the
        # reconciler) are findings about a claim another worker owns; free-text notes otherwise never reach
        # the owner (L61)
        for rf in sorted((meta / "worker-reports").glob("*.json")):
            try:
                notes = str(read_json(rf).get("notes", ""))
            except Exception:
                continue
            for cid, problem in re.findall(r"module claim ([A-Z][A-Z0-9]{1,11}-\d{3,4}):\s*(.+?)(?=module claim [A-Z][A-Z0-9]{1,11}-\d{3,4}:|$)",
                                           notes, flags=re.S):
                if cid.split("-")[0] == prefix.get(mid) and ("note", cid) not in seen:
                    seen.add(("note", cid))
                    add.append({"source": "note", "id": cid, "verdict": "reported", "judge_note": problem.strip()[:1500],
                                "reporter": rf.stem})
        # a failing or stale evidence check means the claim and the code (or the check) disagree: the owner
        # resolves it, by correcting the claim or by fixing a check that was wrong (L65)
        er = meta / "evidence-report.json"
        if er.exists():
            emod = read_json(er).get("modules", {}).get(mid, {})
            for kind in ("failed", "stale"):
                for cid in emod.get(kind, []):
                    if ("evidence", cid) not in seen:
                        seen.add(("evidence", cid))
                        add.append({"source": "evidence", "id": cid, "verdict": kind,
                                    "judge_note": f"_meta/evidence/{mid}/check_{cid}.py is {kind}: run it, then fix the "
                                                  f"claim, or fix the check if it tests the wrong thing (shared process "
                                                  f"state, timing), keeping its '# text:' line equal to the claim"})
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
            k = key(r)
            if k not in keys and k not in earlier:
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
