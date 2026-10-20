#!/usr/bin/env python3
"""Story audit plumbing (references/audit.md, "Story audit").

  story_probe.py snapshot --specs S --module M --out DIR   # DIR/story.md + DIR/questions.jsonl, no answers
  story_probe.py score --specs S [--module M ...]          # $EVAL/judgments/story + _meta/audit/story

A story-only reader answers every probe of its module from the story alone, in a snapshot that holds
the story and the questions and nothing else (no ledger, no code, no reference answers). A scorer
compares each answer with the probe's reference answer. A story that leads its reader to a
contradicted answer misleads, and fails; the share of probes the story answers is its coverage. A
story judge labels each sentence against the claims it cites; distorted or unsupported sentences fail.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _common import eprint, eval_dir, read_jsonl, write_json, write_jsonl

VERDICTS = ("agree", "partial", "contradict", "not_in_story")
SENTENCE = ("supported", "overstated", "distorted", "unsupported")
# round 2 on LiteLLM: stories at 4.1% and 4.3% overstated still led their readers to contradicted answers,
# half of which trace to an overstated row; one at 2.9% was clean (L79)
MAX_OVERSTATED = 0.03


def everyone_text(story_md: str) -> str:
    """The Everyone layer of a story as plain text: exactly what a reader who picked "Everyone" sees on the
    reader site. Which blocks belong to it is check_story.block_layer, the definition the site uses too
    (L77: a hand-kept copy here dropped every section lead, and persona readers met bare headings)."""
    from check_story import block_layer, parse_story
    st, _ = parse_story(story_md)
    out = [f"# {st['headline']}", "", "## In plain words", *st["plain"], ""]
    if st["words_table"]:
        out += ["## Words you'll see", *[f"- {r['term']}: {r['means']} [{', '.join(r['ids'])}]" for r in st["words_table"]], ""]
    for sec in st["sections"]:
        out += [f"## {sec['title']}", ""]
        for b in sec["blocks"]:
            if block_layer(b) != "everyone":
                continue
            if b["t"] == "p":
                out += [b["md"], ""]
            elif b["t"] == "fig":
                out.append(f"Figure: {b['title']}")
                if b["kind"] == "timeline":
                    lanes = {x["id"]: x["label"] for x in b["lanes"]}
                    out += [f"- {e['time']}: {lanes.get(e['lane'], e['lane'])}: {e['label']}, now {e['state']}" for e in b["events"]]
                else:
                    names = {x["id"]: x["label"] for x in b["nodes"] + b["actors"]}
                    out += [f"- {names.get(e['a'], e['a'])} -> {names.get(e['b'], e['b'])}" + (f" ({e['label']})" if e["label"] else "")
                            for e in b["edges"]]
                out += [f"  Step: {x['title']}: {x['md']}" for x in b["steps"]]
                out.append("")
            elif b["t"] == "path":
                out += [f"{x['n']}. {x['md']}" for x in b["steps"]] + [""]
            else:
                raise ValueError(f"story_probe has no plain rendering for an Everyone block of type {b['t']!r}")
    out += ["## Watch out", *[f"- {w}" for w in st["watch"]]]
    return "\n".join(out) + "\n"


def snapshot(specs: Path, module: str, out: Path, lens: str = "engineer", questions: bool = True) -> int:
    story = specs / "_meta" / "story" / f"{module}.md"
    probes = eval_dir(specs) / "probes" / f"{module}.jsonl"
    if not story.exists() or (questions and not probes.exists()):
        eprint(f"ERROR: need {story}" + (f" and {probes}" if questions else ""))
        return 1
    if out.exists():
        shutil.rmtree(out)
    (out / "_briefs").mkdir(parents=True)
    text = story.read_text(encoding="utf-8")
    (out / "story.md").write_text(everyone_text(text) if lens == "everyone" else text, encoding="utf-8")
    rows = []
    if questions:
        rows = [{"id": p["id"], "question": p["question"]} for p in read_jsonl(probes)]
        write_jsonl(out / "questions.jsonl", rows)
    eprint(f"story snapshot: {module}: {lens} layer" + (f" + {len(rows)} questions (no reference answers)" if questions else "")
           + f" -> {out}")
    return 0


def score(specs: Path, modules: list[str]) -> int:
    ev = eval_dir(specs)
    jdir, adir = ev / "judgments" / "story", specs / "_meta" / "audit" / "story"
    mods = modules or sorted({p.stem for p in jdir.glob("*.jsonl")} | {p.stem for p in adir.glob("*.jsonl")})
    report, bad = {}, 0
    for m in mods:
        r: dict = {"module": m}
        js = read_jsonl(jdir / f"{m}.jsonl") if (jdir / f"{m}.jsonl").exists() else []
        if js:
            n = len(js)
            cnt = {v: sum(j.get("verdict") == v for j in js) for v in VERDICTS}
            r.update({"probes": n, **cnt, "coverage": round((cnt["agree"] + 0.5 * cnt["partial"]) / n, 3),
                      "contradicted": [j["id"] for j in js if j.get("verdict") == "contradict"]})
            if cnt["contradict"]:
                bad += 1
                eprint(f"ERROR: {m}: the story led its reader to {cnt['contradict']} contradicted answer(s): {r['contradicted']}")
            odd = [j for j in js if j.get("verdict") not in VERDICTS]
            if odd:
                bad += 1
                eprint(f"ERROR: {m}: {len(odd)} judgment(s) with an unknown verdict")
        tb = read_jsonl(adir / f"{m}.teachback.jsonl") if (adir / f"{m}.teachback.jsonl").exists() else []
        if tb:
            cnt = {v: sum(x.get("verdict") == v for x in tb) for v in ("correct", "vague", "wrong", "unsupported")}
            r["teachback"] = {"n": len(tb), **cnt}
            if cnt["wrong"]:
                bad += 1
                eprint(f"ERROR: {m}: a reader of the Everyone layer explained {cnt['wrong']} thing(s) wrongly, e.g. "
                       f"{next(x for x in tb if x.get('verdict') == 'wrong').get('statement', '')[:90]!r}")
        ss = read_jsonl(adir / f"{m}.jsonl") if (adir / f"{m}.jsonl").exists() else []
        if ss:
            cnt = {v: sum(x.get("verdict") == v for x in ss) for v in SENTENCE}
            r["sentences"] = {"n": len(ss), **cnt}
            wrong = [x for x in ss if x.get("verdict") in ("distorted", "unsupported")]
            if wrong:
                bad += 1
                eprint(f"ERROR: {m}: {len(wrong)} story sentence(s) distorted or unsupported, e.g. {wrong[0].get('sentence', '')[:90]!r}")
            if len(ss) and cnt["overstated"] / len(ss) > MAX_OVERSTATED:
                bad += 1
                eprint(f"ERROR: {m}: {cnt['overstated']}/{len(ss)} sentences overstate their claims (at most {MAX_OVERSTATED:.0%})")
        if len(r) == 1:
            eprint(f"ERROR: {m}: no story judgments or sentence labels to score")
            bad += 1
        report[m] = r
        if "probes" in r:
            eprint(f"{m}: story answers {r['agree']} of {r['probes']} probes fully, {r['partial']} partly, "
                   f"{r['not_in_story']} not covered, {r['contradict']} contradicted; coverage {r['coverage']:.0%}"
                   + (f"; sentences {r['sentences']}" if "sentences" in r else ""))
    write_json(specs / "_meta" / "story-audit.json", report)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["snapshot", "score"])
    ap.add_argument("--specs", required=True)
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--out", default=None)
    ap.add_argument("--lens", choices=["everyone", "engineer"], default="engineer",
                    help="everyone: the snapshot holds only the Everyone layer (what a non-engineer reads)")
    ap.add_argument("--no-questions", action="store_true", help="a persona snapshot: the story only, no probes")
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    if a.cmd == "snapshot":
        if len(a.module) != 1 or not a.out:
            raise SystemExit("snapshot needs one --module and --out")
        out = Path(a.out).resolve()
        if out == specs or specs in out.parents or eval_dir(specs) in out.parents:
            raise SystemExit("the snapshot must live outside the specs and eval dirs")
        return snapshot(specs, a.module[0], out, a.lens, not a.no_questions)
    return score(specs, a.module)


if __name__ == "__main__":
    raise SystemExit(main())
