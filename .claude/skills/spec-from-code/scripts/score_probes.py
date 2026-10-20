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
import re
from pathlib import Path

from _common import eprint, read_json, read_jsonl, write_json, write_jsonl

CATEGORIES = {"validation", "error", "branch", "side_effect", "config", "interface", "data", "concurrency", "default"}
VERDICTS = {"agree", "contradict", "gap", "probe_invalid"}


LITERAL_RES = [
    re.compile(r"`([^`\n]{4,80})`"),                 # backticked literals
    re.compile(r"\"([^\"\n]{5,80})\""),             # double-quoted strings
    re.compile(r"'([^'\n]{5,80})'"),                 # single-quoted strings
    re.compile(r"\b(\d{3,}(?:\.\d+)?)\b"),            # numbers with 3+ digits
    re.compile(r"\b([a-z]+_[a-z0-9_]{3,})\b"),         # snake_case identifiers
    re.compile(r"\b([a-z]+[A-Z][A-Za-z0-9]{3,})\b"),   # camelCase identifiers
]


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?")


def tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text or "")}


def distinctive_token(t: str) -> bool:
    return (t.isdigit() and len(t) >= 3) or (len(t) >= 5 and any(c.isalpha() for c in t))


def distinctive_literals(text: str) -> set[str]:
    out = set()
    for rx in LITERAL_RES:
        for m in rx.findall(text or ""):
            lit = m.strip()
            if len(lit) >= 4 and not lit.isspace():
                out.add(lit)
    return out


def split_for(pid: str) -> str:
    h = int(hashlib.sha1(pid.encode()).hexdigest(), 16) % 10
    return "revision" if h < 6 else "holdout"


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return max(0.0, (c - m) / d)


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
    ap.add_argument("--snapshot", default=None,
                    help="the spec snapshot answerers read this round; used for leak detection (default: specs dir)")
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
                    r["split"] = None
                    n += 1
            # exact split: sort this module's probe ids by hash, hold out the first 40% (rounded up)
            unsplit = [r for r in rows if r.get("split") in (None, "")]
            if unsplit and len(unsplit) == len(rows):
                order = sorted(rows, key=lambda r: hashlib.sha1(r["id"].encode()).hexdigest())
                k = -(-len(rows) * 4 // 10)
                hold = {r["id"] for r in order[:k]}
                for r in rows:
                    r["split"] = "holdout" if r["id"] in hold else "revision"
            if len(rows) < args.min_probes:
                errors.append(f"{pf.name}: only {len(rows)} probes; need at least {args.min_probes}")
            for r in rows:
                if not r.get("split"):
                    r["split"] = split_for(r["id"])  # late additions to an already-split module
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
    report = {"round": rnd, "modules": {}, "rounds": prev_rounds, "leak_suspects": []}
    snap_root = Path(args.snapshot).resolve() if args.snapshot else Path(args.specs).resolve()
    # Spec text only: never _meta (reports from earlier rounds quote reference answers) or briefs.
    spec_corpus = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in snap_root.rglob("*.md")
                            if not ({"_briefs", "_meta"} & set(f.relative_to(snap_root).parts)))
    spec_tokens = tokens(spec_corpus)
    side_notes: list[dict] = []
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
            # Leak check: a literal the answer shares with the code-derived reference, that the spec never
            # contains, could only have come from the code (or a lucky guess). Isolation is instruction-
            # based; this makes a breach visible.
            # Token-level: a literal is suspicious only if it carries a distinctive token found in neither
            # the spec nor the question (answers legitimately fill spec templates with the question's values).
            ans_text = str(answers[pid].get("answer", ""))
            allowed = spec_tokens | tokens(p.get("question", ""))
            leaked = []
            for lit in distinctive_literals(p.get("reference_answer", "")):
                if lit not in ans_text:
                    continue
                novel = [t for t in tokens(lit) if distinctive_token(t) and t not in allowed]
                if novel:
                    leaked.append(f"{lit} (novel: {', '.join(sorted(novel)[:3])})")
            leaked.sort()
            if leaked:
                report["leak_suspects"].append({"module": mid, "probe": pid, "literals": leaked[:5], "verdict": v})
            if v != "agree" and s == "revision":
                failures.append({**p, "answer": answers[pid].get("answer"), "verdict": v, "judge_note": j.get("note", "")})
            elif j.get("spec_defect"):
                # A defect the judge saw that did not flip the verdict. Revision-split ones go to the reviser;
                # held-out ones only to the human report, or the held-out set would leak into revisions.
                if s == "revision":
                    failures.append({**p, "answer": answers[pid].get("answer"), "verdict": "defect_note",
                                     "judge_note": j.get("spec_defect")})
                else:
                    side_notes.append({"module": mid, "probe": pid, "spec_defect": j.get("spec_defect")})
        rf = stats["revision"]["agree"] / stats["revision"]["n"] if stats["revision"]["n"] else 0.0
        hf = stats["holdout"]["agree"] / stats["holdout"]["n"] if stats["holdout"]["n"] else 0.0
        hc = stats["holdout"]["contradict"]
        gaps = stats["revision"]["gap"] + stats["holdout"]["gap"]
        st = status_for(hf, hc)
        prev = prev_rounds.get(str(rnd - 1), {}).get(mid, {})
        prev_hf = prev.get("holdout_fidelity")
        delta = (hf - prev_hf) if isinstance(prev_hf, (int, float)) else None
        # Regression is counted in probes, not points: with ~10 held-out probes one probe is 10 points,
        # so a percentage threshold is noise. Two or more held-out probes lost = regression.
        prev_agree = prev.get("holdout_agree")
        lost = (prev_agree - stats["holdout"]["agree"]) if isinstance(prev_agree, int) else 0
        regression = lost >= 2
        if regression:
            st = "REGRESSION"
        lb = wilson_lower(stats["holdout"]["agree"], stats["holdout"]["n"])
        report["modules"][mid] = {"probes": len(probes), "revision_fidelity": round(rf, 3), "holdout_fidelity": round(hf, 3),
                                  "holdout_contradictions": hc, "gaps": gaps, "invalid_probes": invalid,
                                  "status": st, "delta_holdout": None if delta is None else round(delta, 3),
                                  "holdout_n": stats["holdout"]["n"], "holdout_agree": stats["holdout"]["agree"],
                                  "holdout_wilson_lower": round(lb, 3),
                                  "revision_failures": len(failures)}
        lines.append(f"| {mid} | {len(probes)} | {rf:.0%} | {hf:.0%} ({stats['holdout']['agree']}/{stats['holdout']['n']}, 95% lower {lb:.0%}) | {hc} | {gaps} | {invalid} | {st} | "
                     f"{'' if delta is None else f'{delta:+.0%}'} |")
        if args.failures_for_revision and failures:
            write_jsonl(meta / "revise" / f"round-{rnd}" / f"{mid}.jsonl", failures)
        if invalid and invalid > 0.25 * len(probes):
            errors.append(f"{mid}: {invalid} of {len(probes)} probes judged invalid; re-run the prober")
    report["rounds"][str(rnd)] = {m: {"holdout_fidelity": v["holdout_fidelity"], "holdout_agree": v["holdout_agree"],
                                      "status": v["status"]} for m, v in report["modules"].items()}
    write_json(meta / "validation.json", report)
    lines += ["", "REGRESSION means two or more held-out probes that agreed last round no longer agree: restore that module's "
              "spec from `_meta/rounds/round-<N-1>/` and inspect the revision before trying again. Held-out sets are small "
              "(about 10 probes), so read fidelity with its 95% lower bound, not as a precise number.", ""]
    (meta / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["holdout_side_notes"] = side_notes
    if side_notes:
        lines += ["## Held-out side notes (for the human review; never given to revisers)", ""]
        lines += [f"- {n['module']} {n['probe']}: {n['spec_defect']}" for n in side_notes]
        lines.append("")
        (meta / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_json(meta / "validation.json", report)
    if report["leak_suspects"]:
        lines += ["## Leak suspects", "",
                  "Answers containing a distinctive literal from the code-derived reference that appears nowhere in the "
                  "spec the answerer was given. One or two can be coincidence (a guessable constant); a cluster in one "
                  "module means the answerer read code: discard that module's answers and re-run its answerer.", ""]
        for ls in report["leak_suspects"]:
            lines.append(f"- {ls['module']} {ls['probe']} ({ls['verdict']}): {'; '.join(ls['literals'])}")
        (meta / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_json(meta / "validation.json", report)
        by_mod: dict[str, int] = {}
        for ls in report["leak_suspects"]:
            by_mod[ls["module"]] = by_mod.get(ls["module"], 0) + 1
        for mid, n in by_mod.items():
            if n >= 3:
                errors.append(f"{mid}: {n} answers contain code literals absent from the spec (isolation breach suspected)")
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
