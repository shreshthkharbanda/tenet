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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _common import anchor_tokens, eprint, parse_claims, parse_frontmatter, read_json, read_jsonl, ref_span, write_json

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
    ap.add_argument("--jobs", type=int, default=6, help="checks run in parallel, each in its own working directory")
    ap.add_argument("--list-unbacked", action="store_true")
    ap.add_argument("--repo", default=None, help="repo root, to resolve claim refs (default: _meta/run.json 'repo')")
    ap.add_argument("--no-coverage", action="store_true",
                    help="skip the executed-a-cited-line test (only if coverage.py is unavailable in the run env)")
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
    run_cfg = read_json(specs / "_meta" / "run.json") if (specs / "_meta" / "run.json").exists() else {}
    repo = Path(a.repo or run_cfg.get("repo") or ".").resolve()
    use_cov = not a.no_coverage and subprocess.run([a.python, "-m", "coverage", "--version"], capture_output=True).returncode == 0
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
        runnable = []
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
            runnable.append((cid, fp))

        def spans_of(cid):
            out = []
            for r in mc[cid].get("refs", []):
                sp = ref_span(repo, r)
                if sp:
                    out.append(((repo / sp[0]).resolve(), sp[1], sp[2]))
            return out

        def hollow_reason(cid, fp) -> str | None:
            """A check binds to its claim only if it names something the claim states (L71: assert True,
            a never-called verify(), a self-agreeing reimplementation all passed G7)."""
            body = "\n".join(l for l in fp.read_text(encoding="utf-8", errors="replace").splitlines()
                             if not re.match(r"#\s*(claim|text):", l))
            toks = anchor_tokens(mc[cid]["text"]) | {r.split("::", 1)[1].split(".")[-1] for r in mc[cid].get("refs", []) if "::" in r}
            if toks and not any(t in body for t in toks):
                return "names nothing the claim states (no backticked literal or cited symbol of the claim)"
            return None

        def run_one(item):
            cid, fp = item
            # each check gets its own working directory, so parallel checks never share scratch files
            wd = Path(a.cwd or ".") / f"evidence-{mid}-{cid}"
            wd.mkdir(parents=True, exist_ok=True)
            spans = spans_of(cid)
            cmd = [a.python, "-P", str(fp)]
            if use_cov and spans:
                for old in wd.glob(".coverage*"):
                    old.unlink()
                cmd = [a.python, "-P", "-m", "coverage", "run", "--data-file", str(wd / ".coverage"),
                       "--include", ",".join(sorted({str(sp[0]) for sp in spans})), str(fp)]
            try:
                p = subprocess.run(cmd, cwd=wd, env=env, capture_output=True, text=True, timeout=a.timeout)
            except subprocess.TimeoutExpired:
                return cid, False, ["timeout"]
            ok, tail = p.returncode == 0, (p.stderr or p.stdout).strip().splitlines()[-1:]
            if ok and use_cov and spans:
                # the check must execute at least one line inside a span its claim cites
                j = subprocess.run([a.python, "-m", "coverage", "json", "--data-file", str(wd / ".coverage"),
                                    "-o", str(wd / "cov.json")], cwd=wd, env=env, capture_output=True, text=True)
                executed = {}
                if j.returncode == 0 and (wd / "cov.json").exists():
                    for f, d in json.loads((wd / "cov.json").read_text()).get("files", {}).items():
                        executed[str((wd / f).resolve() if not os.path.isabs(f) else Path(f).resolve())] = set(d.get("executed_lines", []))
                hit = any(lo <= ln <= hi for path, lo, hi in spans for ln in executed.get(str(path), ()))
                if not hit:
                    return cid, None, ["executed no line of the code its claim cites"]
            return cid, ok, tail

        with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
            results = list(pool.map(run_one, runnable))
        by_id = dict(runnable)
        for cid, ok, tail in results:
            why = hollow_reason(cid, by_id[cid]) if ok else None
            if ok is None or why:
                res.setdefault("hollow", []).append(cid)
                errors.append(f"{mid}: check for {cid} is hollow: {why or tail[0]}")
                continue
            if not ok:  # one serial re-run separates a flaky check (load, a port clash) from a wrong claim
                _, ok2, tail2 = run_one((cid, by_id[cid]))
                if ok2:
                    res.setdefault("flaky", []).append(cid)
                    ok = True
                else:
                    tail = tail2
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
    # a --module run updates its modules in the shared report; it never erases the others' results (L70)
    rp = specs / "_meta" / "evidence-report.json"
    if a.module and rp.exists():
        prev = read_json(rp)
        merged = {**prev.get("modules", {}), **report["modules"]}
        kept = [e for e in prev.get("errors", []) if e.split(":", 1)[0] not in report["modules"]]
        write_json(rp, {"modules": merged, "errors": kept + errors})
    else:
        write_json(rp, {**report, "errors": errors})
    if not use_cov:
        eprint("WARN: coverage.py is not available to the run interpreter: checks were not required to execute a "
               "cited line, only to name the claim (install coverage in the run env for the full test)")
    for e in errors[:100]:
        eprint("ERROR:", e)
    for mid, r in report["modules"].items():
        if r["passed"] or r["failed"] or r["tests"] or r["unverifiable"]:
            eprint(f"{mid}: {len(r['passed'])} checks pass ({len(r.get('flaky', []))} only on re-run), {len(r['failed'])} fail, {len(r['stale'])} stale, "
                   f"{r['tests']} test-pinned, {r['unverifiable']} unverifiable; evidence rate {r['evidence_rate']:.0%} "
                   f"of {r['confirmed_normative']} confirmed normative claims")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
