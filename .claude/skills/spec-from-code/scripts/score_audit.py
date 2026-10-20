#!/usr/bin/env python3
"""Phase 8: aggregate adversarial audit outputs into _meta/audit-report.md and _meta/audit.json,
and build the blind sample the judge auditor re-judges.

  score_audit.py <specs> --make-judge-sample --round N [--n 40] [--seed 7]   -> <eval>/audit/judge-sample.jsonl
  score_audit.py <specs> --round N                                          -> report

Pass thresholds (the audit's definition of "good enough to review specs instead of code"):
  falsification (aggregated over all audited modules; 12 samples per module is too few to judge one):
    false claims <= 5%, false or imprecise of medium+ severity <= 10%, and no high-severity failure
  omission: >= 80% of the top behaviors "stated", zero "contradicted", per module
  judges: auditor agreement >= 90%, leniency (original agree, auditor not) <= 5%
  lifecycle: zero "incorrect" steps
  control: lift over the no-spec control >= 0.30 where a control exists
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from _common import eval_dir, eprint, read_json, read_jsonl, write_json, write_jsonl

TH = {"falsify_false": 0.05, "falsify_medium_plus": 0.10, "falsify_high": 0.0, "omission_stated": 0.80,
      "judge_agree": 0.90, "judge_lenient": 0.05, "lift": 0.30}
SEV = {"low": 0, "medium": 1, "high": 2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--make-judge-sample", action="store_true")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    meta = Path(a.specs).resolve() / "_meta"
    audit = meta / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    ev = eval_dir(Path(a.specs))
    eaudit = ev / "audit"  # judge sample and judge audit carry reference answers: eval dir only
    eaudit.mkdir(parents=True, exist_ok=True)
    jdir, adir = ev / "judgments" / f"round-{a.round}", ev / "answers" / f"round-{a.round}"

    if a.make_judge_sample:
        pool = []
        for pf in sorted(p for p in (ev / "probes").glob("*.jsonl") if not p.name.endswith(".questions.jsonl")):
            mid = pf.stem
            if not (adir / f"{mid}.jsonl").exists() or not (jdir / f"{mid}.jsonl").exists():
                continue
            ans = {r["id"]: r for r in read_jsonl(adir / f"{mid}.jsonl")}
            ver = {r["id"]: r["verdict"] for r in read_jsonl(jdir / f"{mid}.jsonl")}
            for p in read_jsonl(pf):
                if p["id"] in ans and ver.get(p["id"]) != "probe_invalid":
                    pool.append((ver.get(p["id"]), {"id": p["id"], "module": mid, "question": p["question"],
                                                    "reference_answer": p["reference_answer"], "refs": p["refs"],
                                                    "answer": ans[p["id"]].get("answer", "")}))
        rng = random.Random(a.seed)
        agrees = [r for v, r in pool if v == "agree"]
        others = [r for v, r in pool if v != "agree"]
        k_agree = min(len(agrees), int(a.n * 0.75))  # leniency hides in "agree": oversample it
        sample = rng.sample(agrees, k_agree) + rng.sample(others, min(len(others), a.n - k_agree))
        rng.shuffle(sample)
        write_jsonl(eaudit / "judge-sample.jsonl", sample)
        eprint(f"judge sample: {len(sample)} rows ({k_agree} originally agree) -> {eaudit / 'judge-sample.jsonl'}")
        return 0

    rep = {"round": a.round, "thresholds": TH, "modules": {}, "checks": {}}
    lines = [f"# Adversarial audit (round {a.round})", ""]
    fails = []
    # falsification + omission per module
    mods = sorted({p.stem.split("-", 1)[1] for p in audit.glob("falsify-*.jsonl")} |
                  {p.stem.split("-", 1)[1] for p in audit.glob("omission-*.jsonl")})
    lines += ["| Module | Claims attacked | False | Imprecise | Severity | Ref wrong | Top behaviors | Stated | Vague | Missing | Contradicted | Omission pass |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    worst = []
    agg = {"n": 0, "false": 0, "med": 0, "high": 0}
    for mid in mods:
        m = {}
        ff = audit / f"falsify-{mid}.jsonl"
        if ff.exists():
            rows = read_jsonl(ff)
            n = len(rows)
            c = {k: sum(1 for r in rows if r.get("verdict") == k) for k in ("holds", "false", "imprecise", "ref_wrong")}
            bad = [r for r in rows if r.get("verdict") in ("false", "imprecise")]
            med = sum(1 for r in bad if SEV.get(r.get("severity", "low"), 0) >= 1)
            hi = sum(1 for r in bad if r.get("severity") == "high")
            m.update(attacked=n, **c, medium_plus=med, high=hi, high_rate=round(hi / n, 3) if n else 0.0)
            agg["n"] += n; agg["false"] += c["false"]; agg["med"] += med; agg["high"] += hi
            worst += [dict(r, module=mid) for r in bad if SEV.get(r.get("severity", "low"), 0) >= 1]
        of = audit / f"omission-{mid}.jsonl"
        if of.exists() and any("spec_status" not in r for r in read_jsonl(of)):
            m["omission"] = "pending"  # step 1 written, step 2 (grading against the spec) not finished
        elif of.exists():
            rows = read_jsonl(of)
            n = len(rows)
            c = {k: sum(1 for r in rows if r.get("spec_status") == k) for k in ("stated", "vague", "missing", "contradicted")}
            m.update(behaviors=n, **{f"om_{k}": v for k, v in c.items()},
                     stated_rate=round(c["stated"] / n, 3) if n else 0.0)
            worst += [dict(r, module=mid, verdict=r.get("spec_status")) for r in rows
                      if r.get("spec_status") in ("missing", "contradicted") and r.get("rank", 99) <= 5]
        ok = m.get("stated_rate", 1) >= TH["omission_stated"] and m.get("om_contradicted", 0) == 0
        m["pass"] = ok
        if not ok:
            fails.append(mid)
        rep["modules"][mid] = m
        lines.append(f"| {mid} | {m.get('attacked', '')} | {m.get('false', '')} | {m.get('imprecise', '')} | "
                     f"{m.get('medium_plus', '')} med+ / {m.get('high', 0)} high | {m.get('ref_wrong', '')} | {m.get('behaviors', m.get('omission', ''))} | {m.get('om_stated', '')} | "
                     f"{m.get('om_vague', '')} | {m.get('om_missing', '')} | {m.get('om_contradicted', '')} | {'yes' if ok else 'NO'} |")
    if agg["n"]:
        fr, mr = agg["false"] / agg["n"], agg["med"] / agg["n"]
        ok = fr <= TH["falsify_false"] and mr <= TH["falsify_medium_plus"] and agg["high"] == 0
        rep["checks"]["falsification"] = {"n": agg["n"], "false_rate": round(fr, 3), "medium_plus_rate": round(mr, 3),
                                          "high": agg["high"], "pass": ok}
        if not ok:
            fails.append("falsification")
        lines += ["", f"Falsification over {agg['n']} sampled claims: {agg['false']} false ({fr:.0%}), {agg['med']} false or "
                  f"imprecise at medium+ severity ({mr:.0%}), {agg['high']} high. {'Pass' if ok else 'FAIL'}."]
    # judge audit
    ja = eaudit / "judge-audit.jsonl"
    if ja.exists():
        aud = {r["id"]: r["verdict"] for r in read_jsonl(ja)}
        orig = {}
        for jf in jdir.glob("*.jsonl"):
            for r in read_jsonl(jf):
                orig[r["id"]] = r["verdict"]
        both = [i for i in aud if i in orig]
        agree = sum(1 for i in both if aud[i] == orig[i])
        lenient = sum(1 for i in both if orig[i] == "agree" and aud[i] != "agree")
        rate, len_rate = (agree / len(both) if both else 0.0), (lenient / len(both) if both else 0.0)
        ok = rate >= TH["judge_agree"] and len_rate <= TH["judge_lenient"]
        rep["checks"]["judges"] = {"n": len(both), "agreement": round(rate, 3), "lenient": round(len_rate, 3), "pass": ok,
                                   "disagreements": [{"id": i, "original": orig[i], "auditor": aud[i]} for i in both if aud[i] != orig[i]]}
        if not ok:
            fails.append("judges")
        lines += ["", f"Judge audit: {agree}/{len(both)} verdicts reproduced ({rate:.0%}); originally-agree verdicts the "
                  f"auditor rejected: {lenient} ({len_rate:.0%}). {'Pass' if ok else 'FAIL'}."]
    # lifecycle
    lc = audit / "lifecycle-check.jsonl"
    if lc.exists():
        rows = read_jsonl(lc)
        c = {k: sum(1 for r in rows if r.get("verdict") == k) for k in ("correct", "incorrect", "vague", "missing", "missing_step_before")}
        ok = c["incorrect"] == 0
        rep["checks"]["lifecycle"] = c | {"pass": ok}
        if not ok:
            fails.append("lifecycle")
        lines += ["", f"Reader lifecycle check: {c['correct']} correct, {c['incorrect']} incorrect, {c['vague']} vague, "
                  f"{c['missing'] + c['missing_step_before']} missing steps. {'Pass' if ok else 'FAIL'}."]
    # control lift
    vj = ev / "validation.json"
    if vj.exists():
        v = read_json(vj)
        lifts = {m: x.get("lift_over_control") for m, x in v.get("modules", {}).items() if x.get("lift_over_control") is not None}
        if lifts:
            low = [m for m, l in lifts.items() if l < TH["lift"]]
            rep["checks"]["control"] = {"lift": lifts, "low": low, "pass": not low}
            if low:
                fails.append("control")
            lines += ["", "Lift over the no-spec control: " + ", ".join(f"{m} {l:+.0%}" for m, l in sorted(lifts.items()))
                      + (f". Below {TH['lift']:.0%}: {', '.join(low)}." if low else ".")]
    if (audit / "redteam.md").exists():
        lines += ["", "Red team findings: see `_meta/audit/redteam.md`; each exploit needs a mechanical fix or a recorded decision."]
    if worst:
        lines += ["", "## Highest-severity findings", ""]
        for w in worst[:25]:
            lines.append(f"- {w['module']} {w.get('id', 'rank ' + str(w.get('rank')))} ({w.get('verdict')}): "
                         f"{(w.get('evidence') or w.get('behavior') or '')[:300]}")
    rep["fails"] = fails
    rep["pass"] = not fails
    lines.insert(2, f"Verdict: {'PASS' if not fails else 'FAIL on ' + ', '.join(fails)}. Thresholds: high-severity "
                    f"falsification <= {TH['falsify_high']:.0%}; top behaviors stated >= {TH['omission_stated']:.0%} with none "
                    f"contradicted; judge agreement >= {TH['judge_agree']:.0%} and leniency <= {TH['judge_lenient']:.0%}; no "
                    f"incorrect lifecycle step; lift over no-spec control >= {TH['lift']:.0%}.\n")
    write_json(meta / "audit.json", rep)
    (meta / "audit-report.md").write_text("\n".join(lines) + "\n")
    eprint(f"audit: {'PASS' if not fails else 'FAIL: ' + ', '.join(fails)} -> _meta/audit-report.md")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
