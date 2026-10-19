#!/usr/bin/env python3
"""Gate G4: fidelity probes (spec-only answers vs code-derived reference answers).

Modes:
  --assign-splits          assign each probe to 'revision' or 'holdout' deterministically (60/40 by id hash),
                           only where 'split' is missing. Run once after probers finish.
  --round N                score answers/judgments for round N, compare with round N-1, write report.
  --failures-for-revision  with --round: write revision-split failures per module to
                           _meta/revise/round-N/<module>.jsonl (never includes holdout probes).

Layout (under specs/_meta):
  probes/<module>.jsonl              {id, module, category, question, reference_answer, refs[]}
  answers/round-N/<module>.jsonl     {id, answer, unanswerable, claims_used[]}
  judgments/round-N/<module>.jsonl   {id, verdict: agree|contradict|gap|probe_invalid, note}
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from _common import eprint, read_json, read_jsonl, write_json, write_jsonl

CATEGORIES = {"validation", "error", "branch", "side_effect", "config", "interface", "data", "concurrency", "default"}
VERDICTS = {"agree", "contradict", "gap", "probe_invalid"}


def split_for(pid: str) -> str:
    h = int(hashlib.sha1(pid.encode()).hexdigest(), 16) % 10
    return "revision" if h < 6 else "holdout"


def status_for(holdout_fidelity: float, holdout_contradictions: int) -> str:
    if holdout_fidelity >= 0.90 and holdout_contradictions == 0:
        return "validated"
    if holdout_fidelity >= 0.75:
        return "provisional"
    return "weak"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--assign-splits", action="store_true")
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--failures-for-revision", action="store_true")
    ap.add_argument("--min-probes", type=int, default=12)
    args = ap.parse_args()
    meta = Path(args.specs).resolve() / "_meta"
    probes_dir = meta / "probes"
    if not probes_dir.exists():
        raise SystemExit("no _meta/probes directory; run probers first")
    errors: list[str] = []

    if args.assign_splits:
        n = 0
        for pf in sorted(probes_dir.glob("*.jsonl")):
            rows = read_jsonl(pf)
            seen = set()
            for r in rows:
                for k in ("id", "module", "question", "reference_answer", "refs", "category"):
                    if k not in r:
                        errors.append(f"{pf.name}: probe missing '{k}': {r.get('id', '?')}")
                if r.get("id") in seen:
                    errors.append(f"{pf.name}: duplicate probe id {r.get('id')}")
                seen.add(r.get("id"))
                if r.get("category") not in CATEGORIES:
                    errors.append(f"{pf.name}: probe {r.get('id')} category {r.get('category')!r} not in {sorted(CATEGORIES)}")
                if not r.get("refs"):
                    errors.append(f"{pf.name}: probe {r.get('id')} has no refs (reference answers must cite code)")
                if "split" not in r:
                    r["split"] = split_for(r["id"])
                    n += 1
            if len(rows) < args.min_probes:
                errors.append(f"{pf.name}: only {len(rows)} probes; need at least {args.min_probes}")
            write_jsonl(pf, rows)
        eprint(f"assigned splits to {n} probes")
        for e in errors:
            eprint("ERROR:", e)
        return 1 if errors else 0

    if args.round is None:
        raise SystemExit("need --assign-splits or --round N")
    rnd = args.round
    ans_dir, jud_dir = meta / "answers" / f"round-{rnd}", meta / "judgments" / f"round-{rnd}"
    prev = meta / "validation.json"
    prev_report = read_json(prev) if prev.exists() else {}
    prev_rounds = prev_report.get("rounds", {})
    report = {"round": rnd, "modules": {}, "rounds": prev_rounds}
    lines = [f"# Validation report (round {rnd})", "",
             "Fidelity = share of probes whose spec-only answer agrees with the code-derived reference answer.",
             "Held-out probes are never shown to spec writers; revision probes drive fixes. "
             "Status: validated >= 0.90 held-out fidelity with zero held-out contradictions; provisional >= 0.75; weak otherwise.", "",
             "| Module | Probes | Revision fidelity | Held-out fidelity | Held-out contradictions | Gaps | Invalid probes | Status | Delta vs prev |",
             "|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for pf in sorted(probes_dir.glob("*.jsonl")):
        mid = pf.stem
        probes = {r["id"]: r for r in read_jsonl(pf)}
        af, jf = ans_dir / f"{mid}.jsonl", jud_dir / f"{mid}.jsonl"
        if not af.exists() or not jf.exists():
            errors.append(f"{mid}: missing answers or judgments for round {rnd}")
            continue
        answers = {r["id"]: r for r in read_jsonl(af)}
        judg = {r["id"]: r for r in read_jsonl(jf)}
        stats = {s: {"n": 0, "agree": 0, "contradict": 0, "gap": 0} for s in ("revision", "holdout")}
        invalid, failures = 0, []
        for pid, p in probes.items():
            j = judg.get(pid)
            if pid not in answers:
                errors.append(f"{mid}: probe {pid} has no answer")
                continue
            if not j:
                errors.append(f"{mid}: probe {pid} has no judgment")
                continue
            v = j.get("verdict")
            if v not in VERDICTS:
                errors.append(f"{mid}: probe {pid} verdict {v!r} invalid")
                continue
            if v == "probe_invalid":
                invalid += 1
                continue
            s = p.get("split") or split_for(pid)
            stats[s]["n"] += 1
            stats[s][v] += 1
            if v != "agree" and s == "revision":
                failures.append({**p, "answer": answers[pid].get("answer"), "verdict": v, "judge_note": j.get("note", "")})
        rf = stats["revision"]["agree"] / stats["revision"]["n"] if stats["revision"]["n"] else 0.0
        hf = stats["holdout"]["agree"] / stats["holdout"]["n"] if stats["holdout"]["n"] else 0.0
        hc = stats["holdout"]["contradict"]
        gaps = stats["revision"]["gap"] + stats["holdout"]["gap"]
        st = status_for(hf, hc)
        prev_hf = prev_rounds.get(str(rnd - 1), {}).get(mid, {}).get("holdout_fidelity")
        delta = (hf - prev_hf) if isinstance(prev_hf, (int, float)) else None
        regression = delta is not None and delta < -0.02
        if regression:
            st = "REGRESSION"
        report["modules"][mid] = {"probes": len(probes), "revision_fidelity": round(rf, 3), "holdout_fidelity": round(hf, 3),
                                  "holdout_contradictions": hc, "gaps": gaps, "invalid_probes": invalid,
                                  "status": st, "delta_holdout": None if delta is None else round(delta, 3),
                                  "revision_failures": len(failures)}
        lines.append(f"| {mid} | {len(probes)} | {rf:.0%} | {hf:.0%} | {hc} | {gaps} | {invalid} | {st} | "
                     f"{'' if delta is None else f'{delta:+.0%}'} |")
        if args.failures_for_revision and failures:
            write_jsonl(meta / "revise" / f"round-{rnd}" / f"{mid}.jsonl", failures)
        if invalid and invalid > 0.25 * len(probes):
            errors.append(f"{mid}: {invalid} of {len(probes)} probes judged invalid; re-run the prober")
    report["rounds"][str(rnd)] = {m: {"holdout_fidelity": v["holdout_fidelity"], "status": v["status"]}
                                  for m, v in report["modules"].items()}
    write_json(meta / "validation.json", report)
    lines += ["", "REGRESSION means held-out fidelity fell by more than 2 points since the previous round: restore that module's "
              "spec from `_meta/rounds/round-<N-1>/` and inspect the revision before trying again.", ""]
    (meta / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for e in errors:
        eprint("ERROR:", e)
    for mid, v in report["modules"].items():
        eprint(f"{mid}: holdout {v['holdout_fidelity']:.0%} ({v['status']}), revision {v['revision_fidelity']:.0%}, "
               f"{v['revision_failures']} revision failures")
    eprint(f"wrote _meta/validation-report.md and _meta/validation.json; "
           f"{'failures written to _meta/revise/round-' + str(rnd) if args.failures_for_revision else ''}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
