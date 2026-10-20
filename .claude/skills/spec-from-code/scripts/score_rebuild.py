#!/usr/bin/env python3
"""Score a rebuild against a baseline, from JUnit XML (pytest --junitxml, Maven surefire,
Gradle, jest-junit, go-junit-report all emit it).

The test suite of a real repository rarely passes 100% in a fresh environment (LiteLLM's router
tests: 47 of 1716 fail on untouched code here). An absolute pass rate would blame the spec for the
environment. So: run the suite on the untouched scratch copy first (baseline), then after the
rebuild; score = share of baseline-passing tests that still pass. The orchestrator runs both, not
the Rebuilder: a worker's test numbers are a claim, the XML is evidence.

Usage: score_rebuild.py --baseline PATH [PATH...] --after PATH [PATH...] --module ID --out specs/_meta/rebuild/ID.score.json
PATH may be an XML file or a directory searched recursively for *.xml.
"""
from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from _common import eprint, write_json


def load(paths: list[str]) -> dict[str, str]:
    files: list[Path] = []
    for p in paths:
        q = Path(p)
        files += sorted(q.rglob("*.xml")) if q.is_dir() else [q]
    out: dict[str, str] = {}
    for f in files:
        try:
            root = ET.parse(f).getroot()
        except (ET.ParseError, OSError):
            continue
        for tc in root.iter("testcase"):
            key = f"{tc.get('classname', '')}::{tc.get('name', '')}"
            if tc.find("failure") is not None or tc.find("error") is not None:
                st = "fail"
            elif tc.find("skipped") is not None:
                st = "skip"
            else:
                st = "pass"
            out[key] = st
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", nargs="+", required=True)
    ap.add_argument("--after", nargs="+", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    base, after = load(args.baseline), load(args.after)
    if not base:
        raise SystemExit("baseline has no test cases; the test command or report path is wrong")
    eligible = [k for k, v in base.items() if v == "pass"]
    still = [k for k in eligible if after.get(k) == "pass"]
    broke = sorted(k for k in eligible if after.get(k) != "pass")
    missing = sorted(k for k in eligible if k not in after)
    newly_fixed = sorted(k for k, v in base.items() if v == "fail" and after.get(k) == "pass")
    collected = len(after) > 0
    score = (len(still) / len(eligible)) if eligible and collected else 0.0
    res = {"module": args.module, "baseline_tests": len(base), "baseline_passing": len(eligible),
           "after_tests": len(after), "still_passing": len(still), "score": round(score, 4),
           "broken": broke[:200], "not_collected": missing[:200], "newly_passing": newly_fixed[:50],
           "collected": collected}
    write_json(Path(args.out), res)
    eprint(f"rebuild {args.module}: {len(still)}/{len(eligible)} baseline-passing tests still pass "
           f"({score:.1%}); {len(missing)} not collected; {len(broke)} broken")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
