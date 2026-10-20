#!/usr/bin/env python3
"""Gate G4: fidelity probes (spec-only answers vs code-derived reference answers).

Modes:
  --assign-splits          assign each probe to 'revision' or 'holdout' deterministically (60/40 by id hash),
                           only where 'split' is missing. Run once after probers finish.
  --round N                score answers/judgments for round N, compare with round N-1, write report.
  --failures-for-revision  with --round: write revision-split failures per module to
                           _meta/revise/round-N/<module>.jsonl (never includes holdout probes).

Layout (under the eval dir, outside specs and repo; see _common.eval_dir):
  probes/<module>.jsonl              {id, module, category, question, reference_answer, refs[]}
  answers/round-N/<module>.jsonl     {id, answer, unanswerable, claims_used[]}
  judgments/round-N/<module>.jsonl   {id, verdict: agree|contradict|gap|probe_invalid, note}
  validation.json, validation-report.md   full report (held-out details); specs/_meta/validation-summary.md
                                          gets the table only, safe for writers to read.

Verdicts are checked, not trusted (L57): agree on an empty or unanswerable answer is an error; agrees whose
answer shares none of the reference's literals are "lenient suspects" (3+ per module is an error); a
held-out probe_invalid counts as a miss unless correct_probe.py logged a correction; "validated" needs at
least --min-holdout valid held-out probes; answers that copy reference phrasing absent from the spec
(3+ novel 6-grams) are counted, and 70%+ of a module's answers doing so is an error.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from _common import eprint, eval_dir, read_json, read_jsonl, resolve_ref, write_json, write_jsonl

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
    # Numbers and hex digests are excluded: answerers legitimately compute them from spec rules and the
    # question's values (sums, 2**64-1, a SHA-256 of a rule-built string). Identifiers and message words
    # cannot be computed, so they remain the leak signal.
    if t.isdigit() or re.fullmatch(r"[0-9a-f]{16,}", t):
        return False
    return len(t) >= 5 and any(c.isalpha() for c in t)


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


def report_lift(rf: float, hf: float, stats: dict, control: float) -> float:
    n = stats["revision"]["n"] + stats["holdout"]["n"]
    return ((rf * stats["revision"]["n"] + hf * stats["holdout"]["n"]) / n if n else 0.0) - control


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return max(0.0, (c - m) / d)


WORD_RE = re.compile(r"[a-z0-9_]+")


def ngrams(text: str, n: int = 6) -> set[tuple]:
    w = WORD_RE.findall((text or "").lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def status_for(holdout_fidelity: float, holdout_contradictions: int, holdout_n: int = 99, min_holdout: int = 0) -> str:
    if holdout_fidelity >= 0.90 and holdout_contradictions == 0 and holdout_n >= min_holdout:
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
    ap.add_argument("--min-holdout", type=int, default=8, help="valid held-out probes needed for 'validated'")
    ap.add_argument("--repo", default=None, help="repo root, to verify probe refs (default: inventory.json repo_root)")
    ap.add_argument("--snapshot", default=None,
                    help="the spec snapshot answerers read this round; used for leak detection (default: specs dir)")
    args = ap.parse_args()
    meta = Path(args.specs).resolve() / "_meta"
    ev = eval_dir(Path(args.specs))
    probes_dir = ev / "probes"
    if not probes_dir.exists():
        raise SystemExit(f"no {probes_dir}; run probers first")
    errors: list[str] = []

    if args.assign_splits:
        n = 0
        inv_path = meta / "inventory.json"
        repo_root = Path(args.repo).resolve() if args.repo else (
            Path(read_json(inv_path)["summary"]["repo_root"]) if inv_path.exists() else Path("."))
        for pf in sorted(p for p in probes_dir.glob("*.jsonl") if not p.name.endswith(".questions.jsonl")):
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
                for ref in r.get("refs", []):
                    ok, why = resolve_ref(repo_root, str(ref))
                    if not ok:
                        errors.append(f"{pf.name}: probe {r.get('id')} ref `{ref}`: {why}")
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
    if args.round == 0:
        raise SystemExit("round 0 is the no-spec control; it is scored as a column of every round >= 1")
    rnd = args.round
    ans_dir, jud_dir = ev / "answers" / f"round-{rnd}", ev / "judgments" / f"round-{rnd}"
    corrected = {r.get("id") for r in read_jsonl(ev / "probe-corrections.jsonl")} if (ev / "probe-corrections.jsonl").exists() else set()
    prev = ev / "validation.json"
    prev_report = read_json(prev) if prev.exists() else {}
    prev_rounds = prev_report.get("rounds", {})
    report = {"round": rnd, "modules": {}, "rounds": prev_rounds, "leak_suspects": []}
    snap_root = Path(args.snapshot).resolve() if args.snapshot else Path(args.specs).resolve()
    # Spec text only: never _meta (reports from earlier rounds quote reference answers) or briefs.
    spec_corpus = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in snap_root.rglob("*.md")
                            if not ({"_briefs", "_meta"} & set(f.relative_to(snap_root).parts)))
    spec_tokens = tokens(spec_corpus)
    spec_grams = ngrams(spec_corpus)
    side_notes: list[dict] = []
    lines = [f"# Validation report (round {rnd})", "",
             "Fidelity = share of probes whose spec-only answer agrees with the code-derived reference answer.",
             "Held-out probes are never shown to spec writers; revision probes drive fixes. No-spec control is the "
             "share answered correctly with no spec at all (prior knowledge); lift is overall fidelity minus that. "
             "Low lift means the probes test what a model already knows, not the spec. "
             "Status: validated >= 0.90 held-out fidelity with zero held-out contradictions; provisional >= 0.75; weak otherwise.", "",
             "| Module | Probes | Revision fidelity | Held-out fidelity | Held-out contradictions | Gaps | Invalid probes | Status | Delta vs prev | No-spec control | Lift |",
             "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|"]
    for pf in sorted(p for p in probes_dir.glob("*.jsonl") if not p.name.endswith(".questions.jsonl")):
        mid = pf.stem
        probes = {r["id"]: r for r in read_jsonl(pf)}
        af, jf = ans_dir / f"{mid}.jsonl", jud_dir / f"{mid}.jsonl"
        if not af.exists() or not jf.exists():
            errors.append(f"{mid}: missing answers or judgments for round {rnd}")
            continue
        answers = {r["id"]: r for r in read_jsonl(af)}
        judg = {r["id"]: r for r in read_jsonl(jf)}
        stats = {s: {"n": 0, "agree": 0, "contradict": 0, "gap": 0} for s in ("revision", "holdout")}
        invalid, failures = {"revision": 0, "holdout": 0}, []
        lenient, copied, answered = [], 0, 0
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
            s = p.get("split") or split_for(pid)
            if v == "probe_invalid":
                invalid[s] += 1
                if s == "holdout" and pid not in corrected:
                    # Dropping a held-out probe from the denominator shrinks the set the score rests on; it
                    # counts as a miss until the probe is corrected (correct_probe.py) and re-judged.
                    stats[s]["n"] += 1
                    stats[s]["gap"] += 1
                continue
            stats[s]["n"] += 1
            stats[s][v] += 1
            ans = answers[pid]
            ans_text = str(ans.get("answer") or "")
            if v == "agree" and (not ans_text.strip() or ans.get("unanswerable") is True):
                errors.append(f"{mid}: probe {pid} judged agree on an empty or unanswerable answer")
            ref_lits = distinctive_literals(p.get("reference_answer", ""))
            if v == "agree" and ref_lits and not any(l.lower() in ans_text.lower() for l in ref_lits):
                lenient.append(pid)
            if ans_text.strip():
                answered += 1
                novel_grams = (ngrams(ans_text) & ngrams(p.get("reference_answer", ""))) - spec_grams - ngrams(p.get("question", ""))
                if len(novel_grams) >= 3:
                    copied += 1
            # Leak check: a literal the answer shares with the code-derived reference, that the spec never
            # contains, could only have come from the code (or a lucky guess). Isolation is instruction-
            # based; this makes a breach visible.
            # Token-level: a literal is suspicious only if it carries a distinctive token found in neither
            # the spec nor the question (answers legitimately fill spec templates with the question's values).
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
            elif s == "revision" and answers[pid].get("note") and re.search(
                    r"(?i)does not (say|state|list|give|specify)|not (stated|specified|defined)|ambigu|contradict|cannot (say|tell)|unclear",
                    str(answers[pid].get("note"))):
                # The answerer could answer but says the spec was ambiguous or silent: a spec defect even when
                # the verdict agrees. Revision split only, like judge side notes.
                failures.append({**p, "answer": answers[pid].get("answer"), "verdict": "answer_note",
                                 "judge_note": str(answers[pid].get("note"))})
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
        st = status_for(hf, hc, stats["holdout"]["n"], args.min_holdout)
        prev = prev_rounds.get(str(rnd - 1), {}).get(mid, {}) if rnd >= 2 else {}  # round 0 is the no-spec control
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
        control = None
        cj = ev / "judgments" / "round-0" / f"{mid}.jsonl"
        if rnd >= 1 and cj.exists():
            cv = {r["id"]: r.get("verdict") for r in read_jsonl(cj)}
            valid = [pid for pid in probes if cv.get(pid) in ("agree", "contradict", "gap")]
            control = (sum(1 for pid in valid if cv[pid] == "agree") / len(valid)) if valid else None
        report["modules"][mid] = {"probes": len(probes), "revision_fidelity": round(rf, 3), "holdout_fidelity": round(hf, 3),
                                  "holdout_contradictions": hc, "gaps": gaps, "invalid_probes": sum(invalid.values()),
                                  "lenient_suspects": lenient, "copied_answers": copied,
                                  "status": st, "delta_holdout": None if delta is None else round(delta, 3),
                                  "holdout_n": stats["holdout"]["n"], "holdout_agree": stats["holdout"]["agree"],
                                  "holdout_wilson_lower": round(lb, 3),
                                  "control_fidelity": None if control is None else round(control, 3),
                                  "lift_over_control": None if control is None else round((rf * stats["revision"]["n"] + hf * stats["holdout"]["n"]) / max(1, stats["revision"]["n"] + stats["holdout"]["n"]) - control, 3),
                                  "revision_failures": len(failures)}
        lines.append(f"| {mid} | {len(probes)} | {rf:.0%} | {hf:.0%} ({stats['holdout']['agree']}/{stats['holdout']['n']}, 95% lower {lb:.0%}) | {hc} | {gaps} | {sum(invalid.values())} | {st} | "
                     f"{'' if delta is None else f'{delta:+.0%}'} | "
                     f"{'' if control is None else f'{control:.0%}'} | "
                     f"{'' if control is None else f'{report_lift(rf, hf, stats, control):+.0%}'} |")
        if args.failures_for_revision and failures:
            write_jsonl(meta / "revise" / f"round-{rnd}" / f"{mid}.jsonl", failures)
        for sp in ("revision", "holdout"):
            n_sp = sum(1 for q in probes.values() if (q.get("split") or split_for(q["id"])) == sp)
            if invalid[sp] and invalid[sp] > 0.25 * max(1, n_sp):
                errors.append(f"{mid}: {invalid[sp]} of {n_sp} {sp} probes judged invalid; re-run the prober")
        if len(lenient) >= 3:
            errors.append(f"{mid}: {len(lenient)} agree verdicts on answers sharing none of the reference's literals "
                          f"({', '.join(lenient[:6])}); re-judge them strictly")
        if answered and copied >= 0.7 * answered:
            errors.append(f"{mid}: {copied}/{answered} answers copy reference phrasing that is not in the spec "
                          f"(isolation breach suspected); discard and re-run the answerer")
    report["rounds"][str(rnd)] = {m: {"holdout_fidelity": v["holdout_fidelity"], "holdout_agree": v["holdout_agree"],
                                      "status": v["status"]} for m, v in report["modules"].items()}
    write_json(ev / "validation.json", report)
    # writer-safe summary: the table only (no held-out notes, no leak literals)
    (meta / "validation-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    lines += ["", "REGRESSION means two or more held-out probes that agreed last round no longer agree: restore that module's "
              "spec from `_meta/rounds/round-<N-1>/` and inspect the revision before trying again. Held-out sets are small "
              "(about 10 probes), so read fidelity with its 95% lower bound, not as a precise number.", ""]
    (ev / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["holdout_side_notes"] = side_notes
    if side_notes:
        lines += ["## Held-out side notes (for the human review; never given to revisers)", ""]
        lines += [f"- {n['module']} {n['probe']}: {n['spec_defect']}" for n in side_notes]
        lines.append("")
        (ev / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_json(ev / "validation.json", report)
    if report["leak_suspects"]:
        lines += ["## Leak suspects", "",
                  "Answers containing a distinctive literal from the code-derived reference that appears nowhere in the "
                  "spec the answerer was given. One or two can be coincidence (a guessable constant); a cluster in one "
                  "module means the answerer read code: discard that module's answers and re-run its answerer.", ""]
        for ls in report["leak_suspects"]:
            lines.append(f"- {ls['module']} {ls['probe']} ({ls['verdict']}): {'; '.join(ls['literals'])}")
        (ev / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_json(ev / "validation.json", report)
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
    eprint(f"wrote {ev}/validation-report.md and validation.json, _meta/validation-summary.md; "
           f"{'failures written to _meta/revise/round-' + str(rnd) if args.failures_for_revision else ''}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
