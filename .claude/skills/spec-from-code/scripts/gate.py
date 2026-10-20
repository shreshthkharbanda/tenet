#!/usr/bin/env python3
"""Run every mechanical gate that has inputs available and print one status table.
Writes specs/_meta/status.json. Exit 1 if any gate that ran failed.

Usage: gate.py <specs_dir> --repo <root> [--round N] [--transcripts DIR ...]
A gate whose inputs should exist never SKIPs silently (L57): --round with no probes is a FAIL, and G5
runs whenever anything was dispatched (zero reports for a dispatched run is a FAIL).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(name: str, cmd: list[str]) -> tuple[str, int, str]:
    p = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
    tail = "\n".join(p.stderr.strip().splitlines()[-1:]) if p.stderr.strip() else ""
    return name, p.returncode, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--transcripts", action="append", default=[],
                    help="subagent transcript dirs; G5 then checks what workers actually opened")
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    meta = specs / "_meta"
    results = []
    if (meta / "inventory.json").exists() and (meta / "modules.json").exists():
        results.append(run("G1 shards", [str(HERE / "check_shards.py"), "--inventory", str(meta / "inventory.json"),
                                          "--modules", str(meta / "modules.json"), "--out", str(meta / "shards-report.json")]))
    else:
        results.append(("G1 shards", -1, "skipped: need _meta/inventory.json and _meta/modules.json"))
    if any(specs.glob("*.md")) or (specs / "modules").exists():
        results.append(run("G2 lint", [str(HERE / "lint_specs.py"), str(specs), "--repo", args.repo, "--out", str(meta / "lint-report.json")]))
        if (meta / "modules.json").exists():
            results.append(run("G3 coverage", [str(HERE / "check_coverage.py"), str(specs), "--repo", args.repo]))
        if (meta / "modules.json").exists() and any(specs.glob("0[1-4]-*.md")):
            results.append(run("G6 ownership", [str(HERE / "check_ownership.py"), str(specs), "--repo", args.repo]))
    else:
        results.append(("G2 lint", -1, "skipped: no specs yet"))
    sys.path.insert(0, str(HERE))
    from _common import eval_dir, reports_dirs
    if args.round is not None:
        if (eval_dir(specs) / "probes").exists():
            results.append(run("G4 probes", [str(HERE / "score_probes.py"), str(specs), "--round", str(args.round), "--failures-for-revision"]))
        else:
            results.append(("G4 probes", 1, f"FAIL: --round {args.round} asked for but {eval_dir(specs) / 'probes'} does not exist"))
    else:
        results.append(("G4 probes", -1, "skipped: pass --round N after answers and judgments exist"))
    if (meta / "evidence").exists():
        run_cfg = json.loads((meta / "run.json").read_text()) if (meta / "run.json").exists() else {}
        if not run_cfg.get("python"):
            results.append(("G7 evidence", 1, "FAIL: _meta/evidence exists but _meta/run.json has no 'python' (and "
                                             "'run_cwd', 'run_env') to run the checks with"))
        else:
            results.append(run("G7 evidence", [str(HERE / "check_evidence.py"), str(specs), "--python", run_cfg["python"],
                                               *(["--cwd", run_cfg["run_cwd"]] if run_cfg.get("run_cwd") else []),
                                               *[x for k, v in (run_cfg.get("run_env") or {}).items() for x in ("--env", f"{k}={v}")]]))
    if (meta / "dispatch.jsonl").exists() or any(d.exists() for d in reports_dirs(specs)):
        results.append(run("G5 reports", [str(HERE / "verify_reports.py"), str(specs), "--repo", args.repo,
                                          *[x for t in args.transcripts for x in ("--transcripts", t)]]))
    else:
        results.append(("G5 reports", -1, "skipped: nothing dispatched yet"))
    failed = 0
    print(f"{'gate':<14}{'result':<10}summary")
    for name, rc, tail in results:
        status = "SKIP" if rc == -1 else "PASS" if rc == 0 else "FAIL"
        failed += 1 if rc > 0 else 0
        print(f"{name:<14}{status:<10}{tail}")
    (meta).mkdir(parents=True, exist_ok=True)
    (meta / "status.json").write_text(json.dumps({n: {"rc": rc, "summary": t} for n, rc, t in results}, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
