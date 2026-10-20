#!/usr/bin/env python3
"""Gate G7: executable evidence. Re-run every claim's check script and report, per module, how many
{confirmed} claims are backed by an executed check or a pinning test, which checks now fail, and which
are stale (the claim text changed since it was verified).

Why: falsifiers that execute found 9-12% of sampled LiteLLM claims false and about 30% wrong at medium
severity or worse, spread evenly over universal and plain claims, after two rounds of probe-driven
revision (L61). Revision fixes what a probe happens to touch; reading-based extraction states what code
outside the cited lines does (what the provider receives, how a dependency logs, what a sibling path
does) and is wrong there. A claim backed by a script that drives the public entry point and asserts the
observable result is right when written and stays checkable: re-running the evidence after a code change
lists exactly the claims that went stale.

Layout (written by verifiers):
  _meta/evidence/<module>/check_<CLAIM-ID>.py   exits 0 when the claim holds. Header lines:
        # claim: RCALL-056
        # text: <the claim text it verifies, as written in the spec, refs omitted>
  _meta/evidence/<module>/tests.jsonl           {"id": ..., "test": "tests/x.py::test_y", "text": ...}
  _meta/evidence/<module>/unverifiable.jsonl    {"id": ..., "reason": "..."}  (timing, real network, ...)

Usage:
  check_evidence.py <specs> --python PY --cwd REPO [--module ID ...] [--env K=V ...] [--timeout 120]
  check_evidence.py <specs> --list-unbacked --module ID     # confirmed normative claims with no evidence
Writes _meta/evidence-report.json. Exit 1 if any check fails or is stale.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from _common import eprint, parse_claims, parse_frontmatter, read_jsonl, write_json

NORMATIVE = {"Behaviors", "Validation rules", "Error handling", "State and data", "External interactions",
             "Configuration", "Concurrency and ordering", "Public surface"}


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def module_claims(specs: Path) -> dict[str, dict]:
    out = {}
    for fp in sorted((specs / "modules").glob("*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        out[fm.get("module") or fp.stem] = {c["id"]: c for c in parse_claims(body)}
    return out


def header(fp: Path) -> tuple[str | None, str | None]:
    cid = text = None
    for ln in fp.read_text(encoding="utf-8", errors="replace").splitlines()[:20]:
        m = re.match(r"#\s*claim:\s*(\S+)", ln)
        if m:
            cid = m.group(1)
        m = re.match(r"#\s*text:\s*(.*)$", ln)
        if m:
            text = m.group(1)
    return cid, text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--python", default="python3")
    ap.add_argument("--cwd", default=None, help="directory the checks run in (the repo root)")
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--list-unbacked", action="store_true")
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    edir = specs / "_meta" / "evidence"
    claims = module_claims(specs)
    mods = a.module or sorted(claims)
    if a.list_unbacked:
        for mid in mods:
            have = {p.stem[len("check_"):] for p in (edir / mid).glob("check_*.py")}
            have |= {r["id"] for f in ("tests.jsonl", "unverifiable.jsonl") if (edir / mid / f).exists()
                     for r in read_jsonl(edir / mid / f)}
            for cid, c in claims.get(mid, {}).items():
                if c["confidence"] == "confirmed" and c["section"] in NORMATIVE and cid not in have:
                    print(f"{mid}\t{cid}")
        return 0
    env = dict(os.environ)
    for kv in a.env:
        k, _, v = kv.partition("=")
        env[k] = v
    report, errors = {"modules": {}}, []
    for mid in mods:
        mc = claims.get(mid, {})
        conf = {cid for cid, c in mc.items() if c["confidence"] == "confirmed" and c["section"] in NORMATIVE}
        res = {"confirmed_normative": len(conf), "passed": [], "failed": [], "stale": [], "orphan": [],
               "tests": 0, "unverifiable": 0}
        for fp in sorted((edir / mid).glob("check_*.py")):
            cid, text = header(fp)
            cid = cid or fp.stem[len("check_"):]
            if cid not in mc:
                res["orphan"].append(cid)
                errors.append(f"{mid}: evidence {fp.name} names {cid}, which is not a claim of this module")
                continue
            if text is None or norm(text) != norm(mc[cid]["text"]):
                res["stale"].append(cid)
                errors.append(f"{mid}: {cid} changed since it was verified (or its check has no '# text:' header); re-verify")
                continue
            try:
                p = subprocess.run([a.python, "-P", str(fp)], cwd=a.cwd, env=env, capture_output=True, text=True,
                                   timeout=a.timeout)
                ok, tail = p.returncode == 0, (p.stderr or p.stdout).strip().splitlines()[-1:]
            except subprocess.TimeoutExpired:
                ok, tail = False, ["timeout"]
            (res["passed"] if ok else res["failed"]).append(cid)
            if not ok:
                errors.append(f"{mid}: check for {cid} fails: {tail[0][:200] if tail else ''}")
        for name, key in (("tests.jsonl", "tests"), ("unverifiable.jsonl", "unverifiable")):
            f = edir / mid / name
            if f.exists():
                rows = [r for r in read_jsonl(f) if r.get("id") in mc]
                res[key] = len(rows)
                if key == "tests":
                    for r in rows:
                        if r.get("text") is not None and norm(r["text"]) != norm(mc[r["id"]]["text"]):
                            res["stale"].append(r["id"])
                            errors.append(f"{mid}: {r['id']} changed since its pinning test was recorded; re-verify")
        backed = len({c for c in res["passed"] if c in conf}) + res["tests"]
        res["evidence_rate"] = round(backed / len(conf), 3) if conf else None
        report["modules"][mid] = res
    write_json(specs / "_meta" / "evidence-report.json", {**report, "errors": errors})
    for e in errors[:100]:
        eprint("ERROR:", e)
    for mid, r in report["modules"].items():
        if r["passed"] or r["failed"] or r["tests"] or r["unverifiable"]:
            eprint(f"{mid}: {len(r['passed'])} checks pass, {len(r['failed'])} fail, {len(r['stale'])} stale, "
                   f"{r['tests']} test-pinned, {r['unverifiable']} unverifiable; evidence rate {r['evidence_rate']:.0%} "
                   f"of {r['confirmed_normative']} confirmed normative claims")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
