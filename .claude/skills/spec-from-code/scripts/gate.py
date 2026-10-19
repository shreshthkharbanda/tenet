#!/usr/bin/env python3
"""Run every mechanical gate that has inputs available and print one status table.
Writes specs/_meta/status.json. Exit 1 if any gate that ran failed.

Usage: gate.py <specs_dir> --repo <root> [--round N]
"""
from __future__ import annotations

import argparse
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
            results.append(run("G3 coverage", [str(HERE / "coverage.py"), str(specs), "--repo", args.repo]))
    else:
        results.append(("G2 lint", -1, "skipped: no specs yet"))
    if args.round is not None and (meta / "probes").exists():
        results.append(run("G4 probes", [str(HERE / "score_probes.py"), str(specs), "--round", str(args.round), "--failures-for-revision"]))
    else:
        results.append(("G4 probes", -1, "skipped: pass --round N after answers and judgments exist"))
    if (meta / "worker-reports").exists():
        results.append(run("G5 reports", [str(HERE / "verify_reports.py"), str(specs), "--repo", args.repo]))
    else:
        results.append(("G5 reports", -1, "skipped: no worker reports"))
    failed = 0
    print(f"{'gate':<14}{'result':<10}summary")
    for name, rc, tail in results:
        status = "SKIP" if rc == -1 else "PASS" if rc == 0 else "FAIL"
        failed += 1 if rc > 0 else 0
        print(f"{name:<14}{status:<10}{tail}")
    import json
    (meta).mkdir(parents=True, exist_ok=True)
    (meta / "status.json").write_text(json.dumps({n: {"rc": rc, "summary": t} for n, rc, t in results}, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
