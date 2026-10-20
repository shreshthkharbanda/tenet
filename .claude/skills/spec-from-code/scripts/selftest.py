#!/usr/bin/env python3
"""Regression tests for the gates themselves. Builds a throwaway fixture repo with planted defects
and asserts each gate catches what it must and stays quiet where it must. Run after any change to
scripts/: `python3 selftest.py`. Every learning that changed a script adds a case here.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
FAILS: list[str] = []


def run(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run([PY, str(HERE / args[0]), *args[1:]], capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout + p.stderr


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name + (": " + detail[-800:] if detail else ""))


def git(repo: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="sfc-selftest-"))
    repo, specs = tmp / "repo", tmp / "out-specs"   # deliberately NOT named "specs" (L03)
    (repo / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    big = ["class Big:\n", "    def __init__(self):\n", "        self.x = 1\n", "\n"]
    for i in range(60):
        big += [f"    def m{i}(self, v):\n", f"        if v > {i}:\n", f"            return v - {i}\n", f"        return {i}\n", "\n"]
    (repo / "pkg" / "big.py").write_text("".join(big))
    (repo / "pkg" / "small.py").write_text("def add(\n    a,\n    b,\n):\n    def local_helper():\n        return 0\n    return a + b\n\n\ndef _hidden():\n    return 0\n")
    (repo / "pkg" / "other.py").write_text("def out_of_scope():\n    return 1\n")
    (repo / "tests" / "test_small.py").write_text("from pkg.small import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    git(repo, "init", "-q"); git(repo, "add", "."); git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = specs / "_meta"
    meta.mkdir(parents=True)
    ev = tmp / "eval"  # probes, answers, judgments, validation: outside specs and repo (L57)

    # L01: --include scopes; out-of-scope files stay as context
    rc, out = run("inventory.py", str(repo), "--out", str(meta / "inventory.json"), "--eval", str(repo / "ev"))
    check("L57 eval dir inside the repo is refused", rc != 0 and "inside the repo" in out, out)
    rc, out = run("inventory.py", str(repo), "--out", str(meta / "inventory.json"), "--include", "pkg/big.py", "--include", "pkg/small.py",
                  "--eval", str(ev))
    inv = json.loads((meta / "inventory.json").read_text())
    other = next(f for f in inv["files"] if f["path"] == "pkg/other.py")
    check("L01 include marks out-of-scope files", rc == 0 and other["in_scope"] is False, out)
    check("tests detected", any(f["is_test"] for f in inv["files"] if f["path"] == "tests/test_small.py"))

    # L02: split_file cuts at member boundaries, contiguous
    rc, out = run("split_file.py", str(repo), "pkg/big.py", "--max-loc", "120", "--json")
    sp = json.loads(out[out.index("{"):]) if rc == 0 else {"ranges": []}
    rs = sp["ranges"]
    contiguous = bool(rs) and rs[0]["start"] == 1 and rs[-1]["end"] == sp["lines"] and all(a["end"] + 1 == b["start"] for a, b in zip(rs, rs[1:]))
    lines = (repo / "pkg" / "big.py").read_text().splitlines()
    at_defs = all(lines[r["start"] - 1].lstrip().startswith(("def ", "class ", "@")) for r in rs[1:])
    check("L02 split ranges contiguous and at definitions", contiguous and at_defs and len(rs) >= 2, out)

    ranges = [f"pkg/big.py:{r['start']}-{r['end']}" for r in rs]
    mods = {"commit": head, "modules": [
        {"id": "big-a", "prefix": "BIGA", "name": "Big part A", "globs": ranges[:1]},
        {"id": "big-b", "prefix": "BIGB", "name": "Big part B", "globs": ranges[1:] + ["pkg/small.py"]}],
        "excluded": []}
    (meta / "modules.json").write_text(json.dumps(mods))
    rc, out = run("check_shards.py", "--inventory", str(meta / "inventory.json"), "--modules", str(meta / "modules.json"),
                  "--out", str(meta / "shards-report.json"), "--min-loc", "1")
    check("G1 passes a complete range plan", rc == 0, out)
    mid_fn = json.loads(json.dumps(mods))
    a0 = rs[0]["end"] + 2  # one line inside the next definition
    mid_fn["modules"][0]["globs"] = [f"pkg/big.py:1-{a0 - 1}"]
    mid_fn["modules"][1]["globs"] = [f"pkg/big.py:{a0}-{sp['lines']}", "pkg/small.py"]
    (tmp / "midfn.json").write_text(json.dumps(mid_fn))
    rc, out = run("check_shards.py", "--inventory", str(meta / "inventory.json"), "--modules", str(tmp / "midfn.json"), "--min-loc", "1")
    check("L27 G1 fails a cut inside a definition", rc == 1 and "definition boundary" in out, out)
    gap = json.loads(json.dumps(mods)); gap["modules"][1]["globs"] = ranges[2:] + ["pkg/small.py"] if len(ranges) > 2 else ["pkg/small.py"]
    (tmp / "gap.json").write_text(json.dumps(gap))
    rc, out = run("check_shards.py", "--inventory", str(meta / "inventory.json"), "--modules", str(tmp / "gap.json"), "--min-loc", "1")
    check("G1 fails a range gap", rc == 1 and "not assigned" in out, out)

    # L07: renderer refuses unused inputs; renders every role without leftovers
    rc, out = run("render_briefs.py", "--role", "judge", "--module", "big-a", "--specs", str(specs), "--repo", str(repo),
                  "--scratch", str(tmp / "scratch"), "--scope-note", "x")
    check("L07 renderer refuses a dropped option", rc != 0 and "silently" in out, out)
    ok = True
    for role in (["--role", "surveyor"], ["--role", "extractor", "--all-modules"], ["--role", "prober", "--all-modules"],
                 ["--role", "crosscut", "--kind", "interfaces"], ["--role", "reconciler"], ["--role", "reviser", "--module", "big-a"],
                 ["--role", "judge", "--module", "big-a"], ["--role", "rebuilder", "--module", "big-b"],
                 ["--role", "answerer", "--module", "big-a", "--snapshot", str(tmp / "snap")]):
        rc, out = run("render_briefs.py", *role, "--specs", str(specs), "--repo", str(repo), "--scratch", str(tmp / "scratch"))
        ok &= rc == 0
    check("render every role", ok, out)
    # L45: every brief marker in the docs must load and render (hyphenated names were silently skipped)
    import re as _re
    docs = "".join((HERE.parent / "references" / f).read_text() for f in ("briefs.md", "audit.md"))
    markers = sorted(set(_re.findall(r"<!-- brief:([^ ]+) -->", docs)))
    sets = ["--set", "SAMPLE_FILE=/x", "--set", "CONTROL_DIR=" + str(tmp / "ctl"), "--set", "READER_SCENARIO=x", "--set", "PERSONA=x"]
    bad = []
    for mk in markers:
        if mk in ("pairjudge",):
            continue  # needs an overlaps file; rendered in the L33 case
        extra = ["--kind", "interfaces"] if mk == "crosscut" else (["--module", "big-a"] if mk not in (
            "surveyor", "reconciler", "control", "judge-auditor", "redteam", "reader", "lifecycle-checker") else [])
        if mk in ("answerer", "story-reader", "persona-reader"):
            extra += ["--snapshot", str(tmp / "snap-x")]
        rc_, out_ = run("render_briefs.py", "--role", mk, *extra, *sets, "--specs", str(specs), "--repo", str(repo),
                        "--scratch", str(tmp / "scratch"))
        if rc_ != 0:
            bad.append(f"{mk}: {out_.strip().splitlines()[-1] if out_.strip() else rc_}")
    check(f"L45 all {len(markers)} brief markers render", not bad, "; ".join(bad))
    ext = (meta / "briefs" / "extractor-big-a.md").read_text()
    check("ranged module brief carries the range note", "LINE RANGE" in ext and ranges[0] in ext)

    # G2 lint: planted defects caught; a clean spec passes
    (specs / "modules").mkdir()
    sections = ["Purpose", "Scope and boundaries", "Public surface", "Behaviors", "Validation rules", "Error handling",
                "State and data", "External interactions", "Configuration", "Concurrency and ordering",
                "Implementation notes", "Open questions and gaps", "Test evidence"]
    def spec(prefix, module, claims):
        body = "\n".join(f"## {s}\n" + (claims if s == "Behaviors" else "None.") + "\n" for s in sections)
        return f"---\nkind: module\nmodule: {module}\nprefix: {prefix}\ncommit: {head}\nstatus: draft\n---\n# {module}\n\n{body}"
    later = ", ".join(f"`pkg/big.py:{r['start']}-{r['end']}`" for r in rs[1:])
    good_b = ("- [BIGB-001] {confirmed} `pkg/small.py:1-2` `add` returns the sum of its two arguments with no type checks.\n"
              f"- [BIGB-002] {{confirmed}} {later} The later methods of `Big` "
              + " ".join(f"m{i}" for i in range(60)) + " return v minus i when v exceeds i, else i.\n")
    good_a = "- [BIGA-001] {confirmed} `pkg/big.py::Big` `Big` stores 1 in x at construction; methods m0 return v minus 0 when v exceeds 0.\n"
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", good_a))
    (specs / "modules" / "big-b.md").write_text(spec("BIGB", "big-b", good_b))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo))
    check("G2 clean specs pass", rc == 0, out)
    bad = good_a + ("- [BIGA-001] {confirmed} `pkg/big.py:1-99999` duplicate id and line past EOF here.\n"
                    "- [BIGA-002] {inferred} no ref on an inferred claim at all, which must fail.\n"
                    "- [BIGA-003] {confirmed} `pkg/small.py::nope` symbol that does not exist anywhere.\n"
                    "- [BIGA-004] {confirmed} `pkg/small.py:1` Claude wrote this claim, mentioning a model.\n"
                    "- [XX-1] malformed\nsee [BIGZ-001]\napi_key = \"abcdefghijklmnopqrstuvwxyz0123\"\n")
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", bad))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo))
    for needle in ("duplicate claim id", "beyond end", "has no source ref", "not found in", "mentions an AI tool",
                   "does not parse", "does not resolve", "credential literal"):
        check(f"G2 catches: {needle}", rc == 1 and needle in out, out)
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", good_a))
    # L56: --only still resolves pointers against every file and fails a dangling one
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", good_a + "See [BIGB-002] and [BIGB-999].\n"))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo), "--only", "modules/big-a.md")
    check("L56 --only resolves pointers into other files, fails a dangling one",
          rc == 1 and "[BIGB-999] does not resolve" in out and "[BIGB-002]" not in out, out)
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", good_a))

    from _common import parse_claims
    pc = parse_claims("- [AB-001] {confirmed} `pkg/a.py:1-2`, `pkg/b.py::X` `add` returns `3`.\n"
                      "- [AB-002] {inferred} `Router.completion` retries twice.\n"
                      "- [AB-003] {gap} Does it time out?\n"
                      "- [AB-004] {confirmed} `pkg/c.py:3` `os.environ/` pointers are resolved at load.\n")
    check("L19 identifier at text start is not a ref", pc[0]["refs"] == ["pkg/a.py:1-2", "pkg/b.py::X"]
          and pc[0]["text"].startswith("`add`") and pc[1]["refs"] == [] and pc[1]["text"].startswith("`Router")
          and pc[3]["refs"] == ["pkg/c.py:3"] and pc[3]["text"].startswith("`os.environ/`"), json.dumps(pc))

    # L33: pair-judge edits applied by claim ID; id, refs kept; unresolvable -> questions
    (meta / "overlaps.jsonl").write_text(json.dumps({"a": {"file": "modules/big-a.md", "id": "BIGA-001"},
                                                     "b": {"file": "modules/big-b.md", "id": "BIGB-002"}}) + "\n")
    (meta / "reconcile").mkdir(exist_ok=True)
    (meta / "reconcile" / "decisions-00.jsonl").write_text("\n".join(json.dumps(d) for d in [
        {"row": 0, "verdict": "duplicate", "edits": [{"file": "modules/big-a.md", "id": "BIGA-001",
         "text": "`Big` stores 1 in x at construction; method behavior is in [BIGB-002]."}]},
        {"row": 0, "verdict": "unresolvable", "edits": [], "question": "which is intended?", "evidence": "pkg/big.py:1-3"}]) + "\n")
    rc, out = run("apply_claim_edits.py", str(specs))
    txt = (specs / "modules" / "big-a.md").read_text()
    check("L33 edit applied by id, refs kept", rc == 0 and "- [BIGA-001] {confirmed} `pkg/big.py::Big` `Big` stores 1 in x at construction; method behavior is in [BIGB-002]." in txt, out)
    check("L33 unresolvable pair becomes a question", "which is intended?" in (meta / "questions.md").read_text())
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo))
    check("L33 specs still lint after edits", rc == 0, out)
    for k, t in (("01a", "a different rewrite"), ("01b", "yet another rewrite")):
        (meta / "reconcile" / f"decisions-{k}.jsonl").write_text(json.dumps(
            {"row": 0, "verdict": "duplicate", "edits": [{"file": "modules/big-a.md", "id": "BIGA-001", "text": t}]}) + "\n")
    before = (specs / "modules" / "big-a.md").read_text()
    rc, out = run("apply_claim_edits.py", str(specs))
    check("L35 conflicting edits are not applied and fail", rc == 1 and "CONFLICT" in out
          and (specs / "modules" / "big-a.md").read_text() == before, out)
    # a decision row's text may carry its own sub-bullets
    (meta / "reconcile" / "decisions-02.jsonl").write_text(json.dumps({"row": -1, "verdict": "contradiction", "edits": [
        {"file": "modules/big-a.md", "id": "BIGA-001", "text": "`Big` stores 1 in x.\n  - and nothing else"}]}) + "\n")
    rc, out = run("apply_claim_edits.py", str(specs))
    check("decision text keeps its sub-bullets", rc == 0 and "stores 1 in x.\n  - and nothing else" in (specs / "modules" / "big-a.md").read_text(), out)
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo), "--only", "modules/big-a.md")
    check("a claim with sub-bullets from a decision row still lints", rc == 0, out)
    (specs / "modules" / "big-a.md").write_text(before)
    (meta / "reconcile" / "decisions-02.jsonl").unlink()
    # L68: a reviser's row against another module's claim is diverted to that module's worklist, not applied
    (meta / "reconcile" / "decisions-revise-big-b-round-1.jsonl").write_text(json.dumps({"row": -1, "verdict": "contradiction",
        "edits": [{"file": "modules/big-a.md", "id": "BIGA-001", "text": "overwritten by another module"}]}) + "\n")
    rc, out = run("apply_claim_edits.py", str(specs))
    dv = [json.loads(l) for l in (meta / "reconcile" / "diverted.jsonl").read_text().splitlines()]
    check("L68 cross-module reviser row is diverted, not applied", "DIVERTED" in out and dv and dv[-1]["owner"] == "big-a"
          and "overwritten by another module" not in (specs / "modules" / "big-a.md").read_text(), out)
    (meta / "reconcile" / "decisions-revise-big-b-round-1.jsonl").unlink(); (meta / "reconcile" / "diverted.jsonl").unlink()
    # L69: claim IDs are permanent: one in the last round's backup that is gone fails lint
    rb = meta / "rounds" / "round-1"
    rb.mkdir(parents=True, exist_ok=True)
    (rb / "big-a.md").write_text(spec("BIGA", "big-a", good_a + "- [BIGA-002] {gap} Does m59 ever raise?\n"))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo))
    check("L69 a deleted claim ID fails lint", rc == 1 and "BIGA-002 existed at round-1 and was deleted" in out, out)
    shutil.rmtree(meta / "rounds")
    # L58: applied decision files are ledgered and never replayed; a ledgered file that changed is an error
    rc, out = run("apply_claim_edits.py", str(specs))
    check("L58 ledgered decision files are not re-applied", rc == 0 and "none (all in ledger.json)" in out
          and (specs / "modules" / "big-a.md").read_text() == before, out)
    (meta / "reconcile" / "decisions-01a.jsonl").write_text("")
    rc, out = run("apply_claim_edits.py", str(specs), "--dry-run")
    check("L58 a changed ledgered file is an error; dry run writes nothing", rc == 1 and "changed after it was applied" in out
          and json.loads((meta / "reconcile" / "applied.json").read_text())["files"] == [], out)
    for k in ("01a", "01b"):
        (meta / "reconcile" / f"decisions-{k}.jsonl").unlink()
    led = json.loads((meta / "reconcile" / "ledger.json").read_text())
    (meta / "reconcile" / "ledger.json").write_text(json.dumps({k: v for k, v in led.items() if k == "decisions-00.jsonl"}))

    # L36: ownership gate: cross-cutting restatement fails, pointers pass
    xc = ("---\nkind: config\nprefix: CFG\ncommit: " + head + "\nstatus: draft\n---\n# Config\n\n## Settings\n"
          "- [CFG-001] {confirmed} `pkg/small.py:1-2` `add` sums its arguments without checks.\n"
          "- [CFG-002] {confirmed} `pkg/small.py:1-2` `add` behavior is specified in [BIGB-001].\n"
          "- [CFG-003] {confirmed} `pkg/small.py:1-2` `add` sums its arguments, as in [CFG-001].\n\n## Precedence\nNone.\n")
    (specs / "03-config.md").write_text(xc)
    rc, out = run("check_ownership.py", str(specs), "--repo", str(repo), "--max-restated", "0.4")
    own_r = json.loads((meta / "ownership.json").read_text())
    check("L36 restating module lines without a pointer to the owner is counted (L56: a pointer to a "
          "cross-cutting claim is not a hand-off)", own_r["03-config.md"]["flagged"] == 2
          and own_r["03-config.md"]["ids"] == ["CFG-001", "CFG-003"] and rc == 1, out)
    (specs / "03-config.md").unlink()

    # L08: freshness is per cited file
    (repo / "README.md").write_text("unrelated\n")
    git(repo, "add", "."); git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "readme")
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo))
    check("L08 unrelated commit is not stale", rc == 0 and "stale" not in out, out)
    (repo / "pkg" / "small.py").write_text("def add(a, b):\n    def local_helper():\n        return 0\n    return a + b  # changed\n\n\ndef _hidden():\n    return 0\n")
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo))
    check("L08 cited-file change is stale", "stale" in out, out)

    # G3 coverage with ranges: range-scoped symbols
    rc, out = run("check_coverage.py", str(specs), "--repo", str(repo), "--min-symbol", "0.5")
    cov = json.loads((meta / "coverage.json").read_text())
    check("G3 range coverage computed per module", cov["modules"]["big-b"]["file_rate"] == 1.0, json.dumps(cov["modules"]["big-b"])[:400])
    check("G3 private symbols ignored", not any("_hidden" in s for s in cov["modules"]["big-b"]["unmentioned_symbols"]))
    (specs / "modules" / "big-b.md").write_text(spec("BIGB", "big-b", good_b.replace("`add` returns", "`small.add` returns")))
    run("check_coverage.py", str(specs), "--repo", str(repo), "--min-symbol", "0.5")
    cq = json.loads((meta / "coverage.json").read_text())["modules"]["big-b"]
    check("L31 qualified mention Class.method counts", not any(s.endswith("::add") for s in cq["unmentioned_symbols"]),
          json.dumps(cq["unmentioned_symbols"]))
    (specs / "modules" / "big-b.md").write_text(spec("BIGB", "big-b", good_b))
    check("L29 nested definitions are not public surface", not any("local_helper" in s for s in cov["modules"]["big-b"]["unmentioned_symbols"]),
          json.dumps(cov["modules"]["big-b"]["unmentioned_symbols"]))

    # G4 probes: exact split, leak detection (true positive and template false positive), side notes, regression
    probes = [{"id": f"BIGA-P{i:02d}", "module": "big-a", "category": "branch", "edge": False,
               "question": f"What does m{i} return for v={i + 7}?", "reference_answer": f"It returns `{7}`.",
               "refs": ["pkg/big.py:5-8"]} for i in range(20)]
    probes[0]["reference_answer"] = "It raises `ZebraOverflowError` with message \"stripes exhausted\""
    (ev / "probes").mkdir(parents=True)
    (ev / "probes" / "big-a.jsonl").write_text("\n".join(json.dumps(p) for p in probes) + "\n")
    rc, out = run("score_probes.py", str(specs), "--assign-splits")
    rows = [json.loads(l) for l in (ev / "probes" / "big-a.jsonl").read_text().splitlines()]
    check("L11 exact 40% held out", sum(r["split"] == "holdout" for r in rows) == 8, out)
    snap = tmp / "snap-r1"
    rc, out = run("snapshot_for_answerers.py", str(specs), "--out", str(snap))
    q = (snap / "_meta" / "probes" / "big-a.questions.jsonl").read_text()
    check("snapshot strips reference answers", rc == 0 and "reference_answer" not in q and not (snap / "_meta" / "probes" / "big-a.jsonl").exists(), out)
    (meta / "probe-corrections.jsonl").write_text(json.dumps({"id": "BIGA-P01", "new": "secret reference"}) + "\n")
    (meta / "reconcile").mkdir(exist_ok=True)
    (meta / "reconcile" / "decisions-zz.jsonl").write_text(json.dumps({"evidence": "code says 42"}) + "\n")
    run("snapshot_for_answerers.py", str(specs), "--out", str(tmp / "snap-leak"))
    leaked = sorted(str(p.relative_to(tmp / "snap-leak")) for p in (tmp / "snap-leak").rglob("*") if p.is_file()
                    and not (p.suffix == ".md" or p.name in ("modules.json",) or p.name.endswith(".questions.jsonl")))
    check("L43 snapshot is an allowlist (no _meta leaks)", leaked == [], str(leaked))
    (meta / "probe-corrections.jsonl").unlink(); (meta / "reconcile" / "decisions-zz.jsonl").unlink()
    for rnd, agree_n in ((1, 20), (2, 17)):
        ad, jd = ev / "answers" / f"round-{rnd}", ev / "judgments" / f"round-{rnd}"
        ad.mkdir(parents=True); jd.mkdir(parents=True)
        ans, jud = [], []
        for i, p in enumerate(rows):
            a = "It returns 7." if i else "ZebraOverflowError(\"stripes exhausted\")"
            ans.append({"id": p["id"], "answer": a, "unanswerable": False, "claims_used": []})
            v = "agree" if i < agree_n or p["split"] == "revision" else "gap"
            j = {"id": p["id"], "verdict": v, "note": ""}
            if i == 3:
                j["spec_defect"] = "states the right result for the wrong reason"
            jud.append(j)
        (ad / "big-a.jsonl").write_text("\n".join(json.dumps(x) for x in ans) + "\n")
        (jd / "big-a.jsonl").write_text("\n".join(json.dumps(x) for x in jud) + "\n")
    rc, out = run("score_probes.py", str(specs), "--round", "1", "--failures-for-revision", "--snapshot", str(snap))
    val = json.loads((ev / "validation.json").read_text())
    leak_ids = [l["probe"] for l in val["leak_suspects"]]
    check("L12 planted leak detected", "BIGA-P00" in leak_ids, json.dumps(val["leak_suspects"]))
    check("L15 template answers not flagged", leak_ids == ["BIGA-P00"], json.dumps(val["leak_suspects"]))
    p3 = next(r for r in rows if r["id"] == "BIGA-P03")
    if p3["split"] == "revision":
        rev = (meta / "revise" / "round-1" / "big-a.jsonl")
        check("L16 revision side note routed", rev.exists() and "defect_note" in rev.read_text())
    else:
        check("L16 held-out side note kept from revisers", any(n["probe"] == "BIGA-P03" for n in val["holdout_side_notes"]))
    rc, out = run("score_probes.py", str(specs), "--round", "2", "--snapshot", str(snap))
    val2 = json.loads((ev / "validation.json").read_text())
    lost = val2["rounds"]["1"]["big-a"]["holdout_agree"] - val2["modules"]["big-a"]["holdout_agree"]
    check("L11 regression by count", (val2["modules"]["big-a"]["status"] == "REGRESSION") == (lost >= 2), json.dumps(val2["modules"]))

    # L22: no-spec control round 0 feeds a control/lift column; never treated as a previous round
    ctl = tmp / "control"
    rc, out = run("snapshot_for_answerers.py", str(specs), "--out", str(ctl), "--questions-only")
    files = sorted(p.name for p in ctl.rglob("*") if p.is_file())
    check("L22 control snapshot holds questions only", files == ["big-a.questions.jsonl"], str(files))
    (ev / "judgments" / "round-0").mkdir(parents=True)
    (ev / "judgments" / "round-0" / "big-a.jsonl").write_text("\n".join(
        json.dumps({"id": r["id"], "verdict": "agree" if i < 5 else "gap"}) for i, r in enumerate(rows)) + "\n")
    rc, out = run("score_probes.py", str(specs), "--round", "0")
    check("L22 round 0 cannot be scored as a round", rc != 0, out)
    rc, out = run("score_probes.py", str(specs), "--round", "1", "--snapshot", str(snap))
    v1 = json.loads((ev / "validation.json").read_text())["modules"]["big-a"]
    check("L22 control fidelity and lift reported", v1.get("control_fidelity") == 0.25 and v1.get("lift_over_control") is not None
          and v1["status"] != "REGRESSION", json.dumps(v1))

    # L22: audit scorer thresholds
    aud = meta / "audit" / "round-1"
    aud.mkdir(parents=True)
    (aud / "falsify-big-a.jsonl").write_text("\n".join(json.dumps({"id": f"BIGA-{i:03d}", "verdict": v, "severity": "high"})
                                                      for i, v in enumerate(["holds"] * 9 + ["false"])) + "\n")
    (aud / "omission-big-a.jsonl").write_text("\n".join(json.dumps({"rank": i, "behavior": "b", "spec_status": s})
                                                       for i, s in enumerate(["stated"] * 9 + ["missing"], 1)) + "\n")
    rc, out = run("score_audit.py", str(specs), "--round", "1")
    a1 = json.loads((meta / "audit.json").read_text())
    check("L52 audit fails on a high-severity falsification", rc == 1 and "falsification" in a1["fails"], out)
    (aud / "omission-big-a.jsonl").write_text(json.dumps({"rank": 1, "behavior": "b"}) + "\n")  # step 1 only
    rc, out = run("score_audit.py", str(specs), "--round", "1")
    a2 = json.loads((meta / "audit.json").read_text())
    check("L52 ungraded omission rows read as pending, not failure", a2["modules"]["big-a"].get("omission") == "pending"
          and "big-a" not in a2["fails"], json.dumps(a2["modules"]["big-a"]))
    (aud / "falsify-big-a.jsonl").write_text("\n".join(json.dumps({"id": f"BIGA-{i:03d}", "verdict": "holds", "severity": "low"}) for i in range(10)) + "\n")
    rc, out = run("score_audit.py", str(specs), "--round", "1", "--make-judge-sample", "--n", "6")
    js = [json.loads(l) for l in (ev / "audit" / "round-1" / "judge-sample.jsonl").read_text().splitlines()]
    check("L22 judge sample is blind", js and all("verdict" not in r for r in js), str(js[:1]))

    # G5 + L03/L17: isolation checks with a specs dir not named "specs"; relative output paths resolve
    wr = meta / "worker-reports"
    wr.mkdir()
    (wr / "prober-big-a.json").write_text(json.dumps({"role": "prober", "module": "big-a", "outputs": [{"path": str(ev / "probes" / "big-a.jsonl")}],
                                                    "files_read": ["pkg/big.py", str(specs / "modules" / "big-a.md")]}))
    (wr / "answerer-big-a-round-1.json").write_text(json.dumps({"role": "answerer", "module": "big-a", "snapshot": str(snap),
                                                              "outputs": [{"path": str(ev / "answers" / "round-1" / "big-a.jsonl")}],
                                                              "files_read": [str(snap / "modules" / "big-a.md"), "pkg/big.py"]}))
    (wr / "extractor-big-b.json").write_text(json.dumps({"role": "extractor", "module": "big-b",
                                                       "outputs": [{"path": f"{specs.name}/modules/big-b.md", "claims": 2}],
                                                       "files_read": ["pkg/small.py"]}))
    (tmp / "reads.txt").write_text(str(repo / "pkg" / "small.py") + "\n")
    rc, out = run("write_report.py", "--specs", str(specs), "--role", "judge", "--module", "big-a", "--round", "1",
                  "--output", str(ev / "probes" / "big-a.jsonl"), "--read-from", str(tmp / "reads.txt"),
                  "--bug", "pkg/small.py:1-2|adds without checks|read")
    wr_ok = json.loads(Path(out.strip().splitlines()[-1]).read_text())
    check("L41 write_report emits the verified schema", rc == 0 and wr_ok["role"] == "judge" and wr_ok["files_read"]
          and wr_ok["suspected_bugs"][0]["where"] == "pkg/small.py:1-2", out)
    (wr / "hand-written.json").write_text(json.dumps({"worker": "x", "inputs": []}))
    rc, out = run("verify_reports.py", str(specs), "--repo", str(repo))
    check("L41 hand-made schema is reported, not crashed on", "write_report.py" in out and "Traceback" not in out, out)
    (wr / "hand-written.json").unlink()
    check("L03 prober reading spec caught (dir not named specs)", "blindness broken" in out, out)
    check("L03 answerer reading source caught", "outside its snapshot" in out, out)
    check("L17 relative output path resolves", "extractor-big-b.json: reported output" not in out, out)

    # L57: verdicts are checked, not trusted (red team: empty/hedged agrees, held-out shrinkage, copying)
    v_before = json.loads((ev / "validation.json").read_text())
    rows = [json.loads(l) for l in (ev / "probes" / "big-a.jsonl").read_text().splitlines()]
    hold = [r for r in rows if r["split"] == "holdout"]
    for r in rows:
        r["reference_answer"] = f"It raises `QuuxLimitError` with message \"limit {r['id']} reached for tenant\"."
    (ev / "probes" / "big-a.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    ad, jd = ev / "answers" / "round-3", ev / "judgments" / "round-3"
    ad.mkdir(parents=True); jd.mkdir(parents=True)
    (ad / "big-a.jsonl").write_text("".join(json.dumps({"id": r["id"], "answer": "" if i == 0 else "It may raise an error, as appropriate.",
                                                        "unanswerable": i == 0}) + "\n" for i, r in enumerate(rows)))
    (jd / "big-a.jsonl").write_text("".join(json.dumps({"id": r["id"], "verdict": "agree"}) + "\n" for r in rows))
    rc, out = run("score_probes.py", str(specs), "--round", "3", "--snapshot", str(snap))
    check("L57 agree on an empty answer is an error", rc == 1 and "empty or unanswerable" in out, out)
    check("L57 hedged agrees flagged as lenient", "agree verdicts on answers sharing none" in out, out)
    (ad / "big-a.jsonl").write_text("".join(json.dumps({"id": r["id"], "answer": r["reference_answer"] + " Nothing else is logged for the tenant here."}) + "\n" for r in rows))
    (jd / "big-a.jsonl").write_text("".join(json.dumps({"id": r["id"], "verdict": "probe_invalid" if r in hold[:2] else "agree"}) + "\n" for r in rows))
    rc, out = run("score_probes.py", str(specs), "--round", "3", "--snapshot", str(snap))
    m3 = json.loads((ev / "validation.json").read_text())["modules"]["big-a"]
    check("L57 held-out probe_invalid counts as a miss", m3["holdout_n"] == len(hold) and m3["holdout_agree"] == len(hold) - 2, json.dumps(m3))
    check("L57 copied reference phrasing is an error", "copy reference phrasing" in out, out)
    (ev / "validation.json").write_text(json.dumps(v_before))

    # L57: G5 checks transcripts and the dispatch log, not only self-reports
    tdir = tmp / "transcripts"
    tdir.mkdir()
    def transcript(agent: str, calls: list) -> None:
        lines = []
        for i, (name, inp, res) in enumerate(calls):
            lines.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}})
            lines.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": res}]}})
        (tdir / f"agent-{agent}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    (meta / "briefs").mkdir(exist_ok=True)
    for b in ("reviser-big-a-round-1.md", "prober-big-b.md"):
        (meta / "briefs" / b).write_text("brief")
    rc, out = run("write_report.py", "--specs", str(specs), "--role", "reviser", "--module", "big-a", "--round", "1",
                  "--output", str(specs / "modules" / "big-a.md"), "--read", str(repo / "pkg" / "big.py"))
    for args in (("--role", "reviser", "--module", "big-a", "--brief", str(meta / "briefs" / "reviser-big-a-round-1.md"), "--agent", "rev1"),
                 ("--role", "prober", "--module", "big-b", "--brief", str(meta / "briefs" / "prober-big-b.md"), "--agent", "prb1")):
        run("dispatch.py", "add", "--specs", str(specs), *args)
    for a in ("rev1", "prb1"):
        run("dispatch.py", "done", "--specs", str(specs), "--agent", a)
    transcript("rev1", [("Bash", {"command": f"E={ev}; cat $E/probes/big-a.jsonl | head"}, "...")])
    rc, out = run("verify_reports.py", str(specs), "--repo", str(repo), "--transcripts", str(tdir))
    check("L57 transcript shows a writer reading held-out probes (variable-expanded Bash)",
          rc == 1 and "reviser-big-a-round-1.json: reviser touched the eval dir" in out, out)
    check("L57 a dispatched worker with no report fails G5", "prober-big-b: dispatched as prober" in out, out)
    transcript("rev1", [("Grep", {"pattern": "add", "path": str(tmp)}, f"{ev}/probes/big-a.jsonl:3:add\n{repo}/pkg/small.py:1:def add(")])
    rc, out = run("verify_reports.py", str(specs), "--repo", str(repo), "--transcripts", str(tdir))
    check("L57 a recursive search whose results list held-out files is caught", "reviser touched the eval dir" in out, out)
    # L74: a worker that publishes, pushes or calls a connector acted outside the run
    transcript("rev1", [("Read", {"file_path": str(specs / "modules" / "big-a.md")}, "..."),
                        ("Artifact", {"action": "publish", "file_path": str(specs / "modules" / "big-a.md")}, "Published"),
                        ("Bash", {"command": "cd /x && git push -u origin main"}, "")])
    rc, out = run("verify_reports.py", str(specs), "--repo", str(repo), "--transcripts", str(tdir))
    check("L74 a worker that published a page or pushed is flagged", "acted outside this run" in out and "Artifact(publish)" in out
          and "git push" in out, out)
    brief_txt = (meta / "briefs" / "extractor-big-a.md").read_text()
    check("L74 every rendered brief tells the worker it only writes files", "Never publish a page or artifact" in brief_txt, brief_txt[-400:])
    # L64: a judge reading an earlier round's verdicts is flagged
    (meta / "briefs" / "judge-big-a-round-2.md").write_text("brief")
    run("write_report.py", "--specs", str(specs), "--role", "judge", "--module", "big-a", "--round", "2",
        "--output", str(ev / "probes" / "big-a.jsonl"), "--read", str(repo / "pkg" / "big.py"))
    run("dispatch.py", "add", "--specs", str(specs), "--role", "judge", "--module", "big-a", "--round", "2",
        "--brief", str(meta / "briefs" / "judge-big-a-round-2.md"), "--agent", "jdg2")
    run("dispatch.py", "done", "--specs", str(specs), "--agent", "jdg2")
    transcript("jdg2", [("Read", {"file_path": str(ev / "judgments" / "round-1" / "big-a.jsonl")}, "...")])
    rc, out = run("verify_reports.py", str(specs), "--repo", str(repo), "--transcripts", str(tdir))
    check("L64 a judge reading an earlier round's judgments is flagged", "verdicts must be independent per round" in out, out)
    (ev / "worker-reports" / "judge-big-a-round-2.json").unlink()
    (meta / "dispatch.jsonl").unlink()
    for f in (meta / "worker-reports" / "reviser-big-a-round-1.json",):
        f.unlink()

    # L57: no silent gate skips; correct_probe guards held-out probes; apply_status trusts only passing gates
    shutil.move(str(ev / "probes"), str(tmp / "probes-aside"))
    rc, out = run("gate.py", str(specs), "--repo", str(repo), "--round", "1")
    check("L57 --round with no probes is a FAIL, not a SKIP", "G4 probes" in out and "FAIL" in out.split("G4 probes", 1)[1].splitlines()[0], out)
    shutil.move(str(tmp / "probes-aside"), str(ev / "probes"))
    hid = hold[0]["id"]
    rc, out = run("correct_probe.py", str(specs), "--id", hid, "--question-append", "(x)", "--reason", "r", "--evidence", "pkg/big.py:5-8")
    check("L57 held-out correction needs --allow-holdout", rc != 0 and "held out" in out, out)
    rc, out = run("correct_probe.py", str(specs), "--id", hid, "--question-append", "(x)", "--reason", "r", "--evidence", "trust me",
                  "--allow-holdout")
    check("L57 correction evidence must resolve to code", rc != 0 and "must cite code" in out, out)
    rc, out = run("correct_probe.py", str(specs), "--id", hid, "--question-append", "(x)", "--reason", "r",
                  "--evidence", "`pkg/big.py:5-8`", "--allow-holdout")
    log = json.loads((ev / "probe-corrections.jsonl").read_text().splitlines()[-1])
    check("L57 question edits are logged with old and new text", rc == 0 and log["new_question"].endswith("(x)")
          and log["old_question"] != log["new_question"], out)
    vfake = {"round": 1, "modules": {"big-a": {"status": "validated", "holdout_fidelity": 1.0, "holdout_contradictions": 0}}}
    (ev / "validation.json").write_text(json.dumps(vfake))
    (meta / "status.json").write_text(json.dumps({"G4 probes": {"rc": 1, "summary": "x"}}))
    (specs / "INDEX.md").write_text("# Index\n\n## Status\n| old | table |\n\n## Next\nx\n")
    rc, out = run("apply_status.py", str(specs))
    fm = (specs / "modules" / "big-a.md").read_text()
    check("L57 apply_status never stamps validated over a failed gate", "status: provisional" in fm, fm[:300])
    idx = (specs / "INDEX.md").read_text()
    check("L57 a hand-written Status section is replaced, not duplicated", idx.count("## Status") == 1 and "| old | table |" not in idx
          and "## Next" in idx, idx)
    (meta / "status.json").unlink(); (specs / "INDEX.md").unlink()
    (ev / "validation.json").write_text(json.dumps(v_before))

    # L62: every brief whose worker may execute code gets the run environment; spec-only roles never do
    import re as _re
    btxt = "\n".join((HERE.parent / "references" / f).read_text() for f in ("briefs.md", "audit.md"))
    bodies = dict(_re.findall(r"<!-- brief:([\w-]+) -->\s*\n```[^\n]*\n(.*?)\n```", btxt, _re.S))
    need = {"surveyor", "extractor", "crosscut", "verifier", "pairjudge", "reconciler", "prober", "judge", "reviser",
            "falsifier", "omission", "lifecycle-checker"}
    never = {"answerer", "control", "rebuilder"}  # spec-only readers; a rebuilder's env would import the original
    check("L62 executing roles get {{RUN_ENV}}", all("{{RUN_ENV}}" in bodies[r] for r in need),
          str([r for r in need if "{{RUN_ENV}}" not in bodies[r]]))
    check("L62 spec-only roles never get {{RUN_ENV}}", not any("{{RUN_ENV}}" in bodies[r] for r in never),
          str([r for r in never if "{{RUN_ENV}}" in bodies[r]]))

    # L63: one brief -> report mapping, round-scoped for audits (round-1 outputs were moved by hand and broke
    # their reports' paths)
    from _common import expected_report as _er
    cases = {"audit-falsifier-big-a-round-2.md": "falsifier-big-a-round-2", "audit-redteam-round-2.md": "redteam-all-round-2",
             "reviser-big-a-round-1.md": "reviser-big-a-round-1", "config.md": "config-all", "surveyor.md": "surveyor-all",
             "verifier-big-a-03.md": "verifier-big-a-03", "prober-big-a.md": "prober-big-a"}
    got = {k: _er(Path("/x/_meta/briefs") / k) for k in cases}
    got["rebuild"] = _er(Path("/s/rebuild-big-a/_brief.md")); got["control"] = _er(Path("/s/control/_brief.md"))
    check("L63 brief names map to report names", all(got[k] == v for k, v in cases.items()) and got["rebuild"] == "rebuilder-big-a"
          and got["control"] == "control-all", json.dumps(got))

    # L61: G7 executable evidence: passing, failing, stale and orphan checks
    edir = meta / "evidence" / "big-a"
    edir.mkdir(parents=True)
    txt = next(c["text"] for c in __import__("_common").parse_claims((specs / "modules" / "big-a.md").read_text()) if c["id"] == "BIGA-001")
    (edir / "check_BIGA-001.py").write_text(f"# claim: BIGA-001\n# text: {txt}\nimport sys\nsys.path.insert(0, {str(repo)!r})\n"
                                           "from pkg.big import Big\nassert Big().x == 1\n")
    rc, out = run("check_evidence.py", str(specs), "--module", "big-a", "--python", sys.executable, "--repo", str(repo))
    ev_r = json.loads((meta / "evidence-report.json").read_text())["modules"]["big-a"]
    check("L61 a passing check backs its claim", rc == 0 and ev_r["passed"] == ["BIGA-001"], out)
    before = (meta / "evidence-report.json").read_text()
    rc, out = run("check_evidence.py", str(specs), "--id", "BIGA-001", "--python", sys.executable, "--repo", str(repo))
    check("L71 an --id run re-checks the claim and leaves the shared report alone",
          rc == 0 and (meta / "evidence-report.json").read_text() == before, out)
    # L71: a check that runs the system in a child process is not hollow (coverage follows the child)
    covpy = os.environ.get("SELFTEST_COVERAGE_PYTHON") or sys.executable
    if subprocess.run([covpy, "-P", "-c", "import coverage"], capture_output=True, cwd=tmp).returncode == 0:  # -P: never pick up a script from the cwd
        (edir / "check_BIGA-001.py").write_text(
            f"# claim: BIGA-001\n# text: {txt}\nimport subprocess, sys\n"
            f"code = {f'import sys; sys.path.insert(0, {str(repo)!r}); from pkg.big import Big; assert Big().x == 1'!r}\n"
            "sys.exit(subprocess.run([sys.executable, '-c', code]).returncode)\n")
        # run from the scripts dir: no script here may shadow a package a check imports (the G3 gate was once coverage.py)
        rc, out = run("check_evidence.py", str(specs), "--module", "big-a", "--python", covpy, "--repo", str(repo), cwd=HERE)
        check("L71 a check that drives the code in a child process is not hollow", rc == 0 and "hollow" not in out, out)
        check("L71 no skill script shadows the coverage package", "not available" not in out, out)
    else:
        print("  SKIP L71 child-process coverage: no interpreter with coverage.py (set SELFTEST_COVERAGE_PYTHON)")
    clash = {q.stem for q in HERE.glob("*.py")} & {"coverage", "json", "re", "ast", "typing", "pathlib", "subprocess", "random",
                                                   "html", "string", "inspect", "site", "code", "token", "types", "signal", "pytest", "yaml"}
    check("L71 no script is named after a module the skill or its checks import", not clash, str(clash))
    (edir / "check_BIGA-001.py").write_text(f"# claim: BIGA-001\n# text: {txt}\nassert True\n")
    rc, out = run("check_evidence.py", str(specs), "--module", "big-a", "--python", sys.executable, "--repo", str(repo))
    check("L71 a hollow check (assert True) fails G7", rc == 1 and "is hollow" in out, out)
    rc, out = run("build_revise.py", str(specs), "--repo", str(repo), "--round", "9")
    rows = [json.loads(x) for x in (meta / "revise" / "round-9" / "big-a.jsonl").read_text().splitlines() if x.strip()]
    check("L71 a hollow check goes to the owner's revise worklist",
          any(r.get("source") == "evidence" and r.get("verdict") == "hollow" and r.get("id") == "BIGA-001" for r in rows), out)
    shutil.rmtree(meta / "revise" / "round-9")
    (edir / "check_BIGA-001.py").write_text(f"# claim: BIGA-001\n# text: {txt}\nimport sys\nsys.path.insert(0, {str(repo)!r})\n"
                                           "from pkg.big import Big\nassert Big().x == 2\n")
    rc, out = run("check_evidence.py", str(specs), "--module", "big-a", "--python", sys.executable)
    check("L61 a failing check fails G7", rc == 1 and "check for BIGA-001 fails" in out, out)
    (edir / "check_BIGA-001.py").write_text("# claim: BIGA-001\n# text: some older wording\nimport sys; sys.exit(0)\n")
    (edir / "check_BIGA-999.py").write_text("# claim: BIGA-999\n# text: x\n")
    rc, out = run("check_evidence.py", str(specs), "--module", "big-a", "--python", sys.executable)
    check("L61 changed claim text makes its evidence stale; unknown ids are orphans",
          rc == 1 and "BIGA-001 changed since it was verified" in out and "BIGA-999, which is not a claim" in out, out)
    shutil.rmtree(meta / "evidence")

    # L09/L10: rebuild scoring is baseline-relative
    def junit(path: Path, cases: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f'<testcase classname="t" name="{k}">' + ("" if v == "pass" else "<failure/>") + "</testcase>" for k, v in cases.items())
        path.write_text(f"<testsuite>{body}</testsuite>")
    junit(tmp / "b.xml", {"a": "pass", "b": "pass", "c": "fail"})
    junit(tmp / "x.xml", {"a": "pass", "b": "fail", "c": "fail"})
    rc, out = run("score_rebuild.py", "--baseline", str(tmp / "b.xml"), "--after", str(tmp / "x.xml"), "--module", "m", "--out", str(tmp / "s.json"))
    sc = json.loads((tmp / "s.json").read_text())
    check("L09 rebuild score ignores baseline failures", sc["score"] == 0.5 and sc["baseline_passing"] == 2, out)

    # L59 (round-1 red team): gates check what refs point at, not only that they resolve
    a_lo, a_hi = rs[0]["start"], rs[0]["end"]
    big_lines = (repo / "pkg" / "big.py").read_text().splitlines()
    k = next(i for i in range(10, 60) if a_lo <= big_lines.index(f"    def m{i}(self, v):") + 1 <= a_hi - 3)
    dk = big_lines.index(f"    def m{k}(self, v):") + 1
    mk = f"`pkg/big.py:{dk}-{dk + 3}`"
    anchored = f"- [BIGA-002] {{confirmed}} {mk} `m{k}` returns `v - {k}` when v exceeds `{k}`, else `{k}`.\n"
    chunks = "".join(f"- [BIGA-{10 + n:03d}] {{confirmed}} `pkg/big.py:{s}-{min(s + 99, a_hi)}` Chunk {n}: each method "
                     f"`mN` here returns v minus N when v exceeds N, else N (part {n}).\n"
                     for n, s in enumerate(range(a_lo, a_hi + 1, 100)))
    head_a = "- [BIGA-001] {confirmed} `pkg/big.py:1-3` `Big` stores `1` in `x` at construction.\n"
    cov_args = ("check_coverage.py", str(specs), "--repo", str(repo), "--min-file", "0", "--min-symbol", "0")
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored + chunks))
    rc, out = run(*cov_args)
    ca = json.loads((meta / "coverage.json").read_text())["modules"]["big-a"]
    check("L59 full range: line coverage passes", ca["line_rate"] >= 0.95 and ca["ok"], json.dumps(ca)[:500])
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored))
    rc, out = run(*cov_args)
    ca = json.loads((meta / "coverage.json").read_text())["modules"]["big-a"]
    check("L59 truncated spec fails line coverage", not ca["ok"] and ca["line_rate"] < 0.6 and "lines" in out
          and ca["uncovered_stretches"], out)
    stray = f"- [BIGA-003] {{confirmed}} `pkg/big.py:1-2` `m{k}` returns `v - {k}` when v exceeds `{k}`.\n"
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored + chunks + stray))
    rc, out = run(*cov_args)
    ca = json.loads((meta / "coverage.json").read_text())["modules"]["big-a"]
    check("L59 a ref pointing away from the claim's tokens is unanchored; rate gates the module",
          ca["unanchored"] == ["BIGA-003"] and not ca["ok"] and "unanchored" in out, json.dumps(ca)[:500])
    # cross-cutting refs no longer satisfy a module's file coverage; symbols in HTML comments do not count
    only_big = "".join(f"- [BIGB-{n + 1:03d}] {{confirmed}} `pkg/big.py:{r['start']}-{r['end']}` `Big` methods here return "
                       f"v minus i when v exceeds i (range {n}).\n" for n, r in enumerate(rs[1:]))
    (specs / "modules" / "big-b.md").write_text(spec("BIGB", "big-b", only_big + "<!-- add -->\n"))
    xc_cfg = ("---\nkind: config\nprefix: CFG\ncommit: " + head + "\nstatus: draft\n---\n# Config\n\n## Settings\n"
              "- [CFG-001] {confirmed} `pkg/small.py:1-2` `add` takes two arguments.\n\n## Precedence\nNone.\n")
    (specs / "03-config.md").write_text(xc_cfg)
    run(*cov_args)
    cb = json.loads((meta / "coverage.json").read_text())["modules"]["big-b"]
    check("L59 cross-cutting refs do not cover a module's file", "pkg/small.py" in cb["uncovered_files"], json.dumps(cb)[:400])
    check("L59 a symbol named only in an HTML comment is unmentioned", "pkg/small.py::add" in cb["unmentioned_symbols"],
          json.dumps(cb["unmentioned_symbols"]))
    # G2: duplicate text, unfalsifiable phrases, symbol refs naming no definition, wide refs, unknown commit
    lint_bad = (head_a + anchored + chunks
                + f"- [BIGA-004] {{confirmed}} {mk} `m{k}` returns `v - {k}` when v exceeds `{k}`, else `{k}`.\n"
                + "- [BIGA-005] {confirmed} `pkg/big.py:1-3` Handles this case appropriately and returns the result.\n"
                + "- [BIGA-006] {confirmed} `pkg/big.py::return` `Big` keeps its state.\n"
                + f"- [BIGA-007] {{confirmed}} `pkg/big.py::Big.m{k}` `m{k}` compares `v` with `{k}` first.\n"
                + f"- [BIGA-008] {{confirmed}} `pkg/big.py:1-{a_hi}` `Big` defines the methods of this range.\n")
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", lint_bad))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo), "--only", "modules/big-a.md")
    check("L59 G2 catches repeated claim text", rc == 1 and "BIGA-004 repeats the text of BIGA-002" in out, out)
    check("L59 G2 catches an unfalsifiable stock phrase", "BIGA-005 says 'appropriately'" in out, out)
    check("L59 G2 catches a symbol ref naming no definition, accepts Class.method",
          "BIGA-006 ref `pkg/big.py::return`: names no definition" in out and "BIGA-007" not in out, out)
    check("L59 G2 warns on a wide confirmed ref", f"BIGA-008 ref `pkg/big.py:1-{a_hi}` spans" in out, out)
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored).replace(
        f"commit: {head}", "commit: 0123456789abcdef0123456789abcdef01234567"))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo), "--only", "modules/big-a.md")
    check("L59 an unknown commit stamp is an error, not a warning", rc == 1 and "ERROR" in out and "cannot diff" in out, out)
    # reconcile worklist: same-file pairs, and wide refs that share a literal
    same = (head_a + anchored + chunks
            + f"- [BIGA-004] {{confirmed}} {mk} `m{k}` returns `v - {k + 1}` when v exceeds `{k + 1}`.\n"
            + f"- [BIGA-008] {{confirmed}} `pkg/big.py:1-{a_hi}` Across the class, `v - {k}` is what `m{k}` returns.\n"
            + f"- [BIGA-009] {{confirmed}} `pkg/big.py:1-{a_hi}` `Big` has no class attributes besides `x`.\n")
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", same))
    rc, out = run("find_overlaps.py", str(specs), "--repo", str(repo))
    ov = [json.loads(l) for l in (meta / "overlaps.jsonl").read_text().splitlines() if l.strip()]
    ids = {frozenset((r["a"]["id"], r["b"]["id"])): r for r in ov}
    check("L59 same-file claims on the same lines are paired", frozenset(("BIGA-002", "BIGA-004")) in ids, out)
    check("L59 a wide ref pairs only with a claim sharing a literal",
          frozenset(("BIGA-002", "BIGA-008")) in ids and frozenset(("BIGA-002", "BIGA-009")) not in ids, out)
    # G6: a pointer must name a related claim of the owner; a bare path into a split file is owned
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored + chunks))
    own_xc = ("---\nkind: config\nprefix: CFG\ncommit: " + head + "\nstatus: draft\n---\n# Config\n\n## Settings\n"
              f"- [CFG-001] {{confirmed}} {mk} `m{k}` returns `v - {k}` above `{k}`.\n"
              f"- [CFG-002] {{confirmed}} {mk} `m{k}` returns `v - {k}` above `{k}` (context: [BIGA-001]).\n"
              f"- [CFG-003] {{confirmed}} {mk} `m{k}` is specified in [BIGA-002].\n"
              "- [CFG-004] {confirmed} `pkg/big.py` `Big` methods return v minus i when v exceeds i.\n"
              "- [CFG-005] {confirmed} `pkg/big.py:1-3` `Big` starts with `1` in `x`; see [BIGA-001].\n\n## Precedence\nNone.\n")
    (specs / "03-config.md").write_text(own_xc)
    rc, out = run("check_ownership.py", str(specs), "--repo", str(repo), "--max-restated", "0.9")
    own_r = json.loads((meta / "ownership.json").read_text())["03-config.md"]
    check("L59 G6 counts only related pointers; bare refs into a split file are owned",
          own_r["ids"] == ["CFG-001", "CFG-002", "CFG-004"] and own_r["pointers_unrelated"] == 1, json.dumps(own_r))
    (specs / "03-config.md").unlink()
    # L72: G8 chapter stories cite claims that exist and state only what those claims or their code say
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored + chunks))
    sdir = meta / "story"
    sdir.mkdir(parents=True, exist_ok=True)
    good_story = (f"---\nmodule: big-a\n---\n# Big keeps one stored value and each method compares with its own bound\n\n@plain\n"
                  f"A Big object remembers one number from the moment it is made [BIGA-001]. Each of its methods takes a number and "
                  f"compares it with a bound of its own [BIGA-002]. When the number is above the bound, the method gives back the "
                  f"difference, and otherwise it gives back the bound [BIGA-002]. The later methods follow the same rule [BIGA-010].\n\n"
                  f"@minute\nA Big object stores `1` in its stored value when it is built, and keeps it for its whole life [BIGA-001]. "
                  f"Method `m{k}` compares the number it gets with its bound and gives back the difference when the number is larger, "
                  f"or the bound when it is not [BIGA-002]. Every later method in the class follows the same rule with its own bound [BIGA-010].\n\n"
                  f"## Words you'll see\n| Term | Means | In the code | Claims |\n| --- | --- | --- | --- |\n"
                  f"| Big object | the class this chapter describes | `Big` | BIGA-001 |\n| stored value | the number a Big object keeps | `x` | BIGA-001 |\n"
                  f"| method with bound {k} | one of the comparing methods | `m{k}` | BIGA-002 |\n| the result | what the method gives back | `v - {k}` | BIGA-002 |\n\n"
                  f"## Construction always stores one value\nEvery new object starts with the same number [BIGA-001].\n\nWhen a Big object is built, it puts the number `1` into its stored value, `x` [BIGA-001]. "
                  f"Nothing in the class changes that number afterwards [BIGA-001]. So every object starts and stays the same [BIGA-001].\n\n"
                  f"@figure flow id=m-rule title=\"How a method picks its result\"\n| node in | Input number | BIGA-002 |\n"
                  f"| node test | Above the bound? | BIGA-002 |\n| node out | Return the difference | BIGA-002 |\n| in > test | compare | BIGA-002 |\n"
                  f"| test > out | yes | BIGA-002 |\n\n@steps m-rule\n| test | Above the bound? | The method compares the number with its bound [BIGA-002]. |\n"
                  f"| test>out | Return the difference | It gives back the number minus the bound [BIGA-002]. |\n\n"
                  f"## Each method returns the number minus its bound above the bound\nEach method compares a number with a bound of its own [BIGA-002].\n\nThe method with bound `{k}` looks at the number it is given [BIGA-002]. "
                  f"It gives back the number minus that bound, written `v - {k}`, when the number is larger [BIGA-002]. "
                  f"For any smaller number it gives back the bound itself [BIGA-002].\n\n"
                  f"@figure timeline id=ex title=\"Example: one object, two calls\"\n| lane obj | The object |\n"
                  f"| 0s | obj | made | holds one | BIGA-001 |\n| 1s | obj | method called | answered | BIGA-002 |\n\n"
                  f"## The later methods follow the same rule\nEvery method in a chunk follows that rule [BIGA-010].\n\n"
                  f"## Watch out\n- A Big object always starts with the number one [BIGA-001].\n")
    (sdir / "big-a.md").write_text(good_story)
    rc, out = run("check_story.py", str(specs), "--module", "big-a", "--repo", str(repo))
    check("L72 a story that cites real claims and their literals passes G8", rc == 0 and ": 0 errors" in out, out)
    bad_story = (good_story.replace("[BIGA-010].\n\n## Words", "[BIGA-010]. The cache holds `9999` entries [BIGA-001].\n\n## Words")
                 .replace("| in > test | compare | BIGA-002 |", "| in > test | compare | |")
                 .replace("| test>out | Return the difference |", "| test>gone | Return the difference |")
                 .replace("## Watch out\n- A Big object always starts with the number one [BIGA-001].", "## Watch out\n- It retries 3 times.\n- See [BIGA-777]."))
    (sdir / "big-a.md").write_text(bad_story)
    rc, out = run("check_story.py", str(specs), "--module", "big-a", "--repo", str(repo))
    check("L72 G8 catches an invented value, an uncited edge, a dangling step, an uncited number and an unknown ID",
          rc == 1 and "states 9999 found in neither" in out and "edge in>test cites no claim" in out
          and "targets test>gone" in out and "cites no claim: It retries 3 times." in out and "unknown claim BIGA-777" in out, out)
    # L75: the readability standard: no code in the Everyone layer, every code name bridged to a plain term,
    # acronyms spelled out, timelines move forward and are labelled as examples
    worse = (good_story.replace("| node out | Return the difference |", "| node out | Return `v - 1` |")
             .replace("For any smaller number it gives back the bound itself [BIGA-002].", "For any smaller number it calls `big_helper` [BIGA-002].")
             .replace("- A Big object always starts with the number one [BIGA-001].", "- A Big object keeps its TPM at one [BIGA-001].")
             .replace("| 1s | obj | method called |", "| 0.5s | obj | method called |").replace("| 0s | obj | made |", "| 2s | obj | made |")
             .replace('title=\"Example: one object, two calls\"', 'title=\"One object, two calls\"'))
    (sdir / "big-a.md").write_text(worse)
    rc, out = run("check_story.py", str(specs), "--module", "big-a", "--repo", str(repo))
    check("L75 G8 enforces the layers: code in a figure, an undefined code name, an unexplained acronym, a backwards untitled timeline",
          rc == 1 and "uses code formatting" in out and "`big_helper` is not defined in Words you'll see" in out
          and "acronym TPM is never spelled out" in out and "events go back in time" in out and 'starts with "Example:"' in out, out)
    (specs / "00-overview.md").write_text("---\nkind: overview\nprefix: SYS\ncommit: " + head + "\nstatus: draft\n---\n# X: overview\n\n"
                                          "## Main paths\n\n### 1. One call\n1. The object is made [BIGA-001].\n2. A method runs [BIGA-002].\n")
    sys_story = ("---\nmodule: _system\n---\n# Big objects remember a number and compare others with it\n\n@plain\n"
                 "A Big object remembers one number from the moment it is made [BIGA-001]. Its methods compare any number they get with "
                 "a bound of their own and give back the difference when the number is larger [BIGA-002]. Each method has a different "
                 "bound, so the same number can give different answers from different methods [BIGA-002]. Nothing else changes inside "
                 "the object, and the later methods follow the same rule [BIGA-010].\n\n## What happens when a method is called\nFirst the object exists, then a method answers [BIGA-002].\n\n"
                 "@path flow-one-call\n| 1 | The object is made and keeps the number one [BIGA-001]. |\n\n"
                 "## The later methods follow the same rule\nEach later method behaves the same way [BIGA-010].\n\n"
                 "## Watch out\n- The number is always one at the start [BIGA-001].\n")
    (sdir / "_system.md").write_text(sys_story)
    rc, out = run("check_story.py", str(specs), "--module", "_system", "--repo", str(repo))
    check("L75 the system story must give every step of every main path", rc == 1 and "@path flow-one-call has steps [1]; the path has 2" in out, out)
    (sdir / "_system.md").write_text(sys_story.replace("[BIGA-001]. |\n\n## The later", "[BIGA-001]. |\n| 2 | A method compares a number with its bound [BIGA-002]. |\n\n## The later"))
    rc, out = run("check_story.py", str(specs), "--module", "_system", "--repo", str(repo))
    check("L75 a complete system story passes", rc == 0, out)
    (sdir / "_system.md").unlink()
    (specs / "00-overview.md").unlink()
    site = tmp / "site"
    rc, out = run("site_data.py", str(specs), "--out", str(site), "--repo", str(repo))
    fa = json.loads((site / "data" / "f-modules-big-a.json").read_text())
    check("L72 a story failing G8 never reaches the site", fa["story"] is None and "story left out" in out, out)
    (sdir / "big-a.md").write_text(good_story)
    rc, out = run("site_data.py", str(specs), "--out", str(site), "--repo", str(repo))
    fa = json.loads((site / "data" / "f-modules-big-a.json").read_text())
    check("L72 a passing story is compiled with chips as claim links and its figure",
          fa["story"] and 'data-id="BIGA-001"' in fa["story"]["minute"][0]
          and any(b.get("kind") == "flow" for b in fa["story"]["sections"][0]["blocks"])
          and fa["story"]["sections"][0]["blocks"][0].get("lead"), json.dumps(fa.get("story"))[:600])
    # L72 story audit: the reader's snapshot holds the story and the questions, never the answers; a
    # contradicted answer or a distorted sentence fails the score
    from _common import eval_dir as _evd
    evx = _evd(specs)
    (evx / "probes").mkdir(parents=True, exist_ok=True)
    (evx / "probes" / "big-a.jsonl").write_text(json.dumps({"id": "BIGA-P01", "question": "What does Big store in x?",
                                                            "reference_answer": "SECRET-REFERENCE 1", "split": "holdout"}) + "\n")
    snapx = tmp / "story-snap"
    rc, out = run("story_probe.py", "snapshot", "--specs", str(specs), "--module", "big-a", "--out", str(snapx))
    blob = "".join(f.read_text() for f in snapx.rglob("*") if f.is_file())
    check("L72 a story snapshot carries the story and questions but no reference answers",
          rc == 0 and "What does Big store" in blob and "SECRET-REFERENCE" not in blob and (snapx / "story.md").exists(), out)
    snape = tmp / "persona-snap"
    rc, out = run("story_probe.py", "snapshot", "--specs", str(specs), "--module", "big-a", "--lens", "everyone", "--no-questions", "--out", str(snape))
    etext = (snape / "story.md").read_text() if (snape / "story.md").exists() else ""
    check("L75 the Everyone-layer snapshot holds the plain layer only: no code, no Engineer prose, no questions",
          rc == 0 and "remembers one number" in etext and "`" not in etext and "In one minute" not in etext
          and "puts the number" not in etext and not (snape / "questions.jsonl").exists(), etext[:400] + out)
    (evx / "judgments" / "story").mkdir(parents=True, exist_ok=True)
    (evx / "judgments" / "story" / "big-a.jsonl").write_text(json.dumps({"id": "BIGA-P01", "verdict": "contradict", "note": "x"}) + "\n")
    (meta / "audit" / "story").mkdir(parents=True, exist_ok=True)
    (meta / "audit" / "story" / "big-a.jsonl").write_text(json.dumps({"sentence": "s", "ids": ["BIGA-001"], "verdict": "distorted"}) + "\n")
    rc, out = run("story_probe.py", "score", "--specs", str(specs))
    check("L72 a contradicted story answer and a distorted sentence each fail the story audit",
          rc == 1 and "contradicted answer" in out and "distorted or unsupported" in out, out)
    (evx / "judgments" / "story" / "big-a.jsonl").write_text(json.dumps({"id": "BIGA-P01", "verdict": "agree"}) + "\n")
    (meta / "audit" / "story" / "big-a.jsonl").write_text(json.dumps({"sentence": "s", "ids": ["BIGA-001"], "verdict": "supported"}) + "\n")
    rc, out = run("story_probe.py", "score", "--specs", str(specs))
    check("L72 a faithful story that answers its probe passes", rc == 0 and "coverage 100%" in out, out)
    shutil.rmtree(evx / "judgments" / "story"); shutil.rmtree(meta / "audit" / "story"); (evx / "probes" / "big-a.jsonl").unlink()
    shutil.rmtree(sdir)
    # red team B6: a table row citing a claim states a value found in neither the claim nor its code
    rows = ("\n| Claim | Value |\n|---|---|\n| [BIGA-001] | `made_up_setting` |\n"
            "| [BIGA-001] | `self.x` holds it |\n")
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored + chunks + rows))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo), "--only", "modules/big-a.md")
    check("B6 a table row value in neither its claim nor its code is flagged; one the code holds is not",
          "states made_up_setting, found in neither" in out and "states self" not in out, out)
    # red team B7: INDEX.md pointers resolve and it holds no claims; only apply_status sets a status
    idx = specs / "INDEX.md"
    old_idx = idx.read_text() if idx.exists() else None
    idx.write_text("# Index\n\nSee [NOPE-999] and `no/such/file.py:1-9`; `modules/big-a.md` is real.\n\n"
                   "- [IDX-001] {confirmed} `pkg/big.py:1-3` The router never retries.\n")
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", head_a + anchored + chunks).replace("status: draft", "status: validated"))
    rc, out = run("lint_specs.py", str(specs), "--repo", str(repo))
    check("B7 INDEX.md is linted: dangling pointer, unresolvable ref, claims in the index",
          rc == 1 and "INDEX.md: cross-reference [NOPE-999]" in out and "`no/such/file.py:1-9` names no spec file" in out
          and "claim IDX-001 in the index" in out and "modules/big-a.md` names" not in out, out)
    check("B7 a typed status without apply_status's fidelity block is an error",
          "modules/big-a.md: status 'validated' without the fidelity block" in out, out)
    if old_idx is None:
        idx.unlink()
    else:
        idx.write_text(old_idx)
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", good_a))
    (specs / "modules" / "big-b.md").write_text(spec("BIGB", "big-b", good_b))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print(" -", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
