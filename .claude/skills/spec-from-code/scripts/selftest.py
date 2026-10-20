#!/usr/bin/env python3
"""Regression tests for the gates themselves. Builds a throwaway fixture repo with planted defects
and asserts each gate catches what it must and stays quiet where it must. Run after any change to
scripts/: `python3 selftest.py`. Every learning that changed a script adds a case here.
"""
from __future__ import annotations

import json
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
    sets = ["--set", "SAMPLE_FILE=/x", "--set", "CONTROL_DIR=" + str(tmp / "ctl"), "--set", "READER_SCENARIO=x"]
    bad = []
    for mk in markers:
        if mk in ("pairjudge",):
            continue  # needs an overlaps file; rendered in the L33 case
        extra = ["--kind", "interfaces"] if mk == "crosscut" else (["--module", "big-a"] if mk not in (
            "surveyor", "reconciler", "control", "judge-auditor", "redteam", "reader", "lifecycle-checker") else [])
        if mk == "answerer":
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
    rc, out = run("coverage.py", str(specs), "--repo", str(repo), "--min-symbol", "0.5")
    cov = json.loads((meta / "coverage.json").read_text())
    check("G3 range coverage computed per module", cov["modules"]["big-b"]["file_rate"] == 1.0, json.dumps(cov["modules"]["big-b"])[:400])
    check("G3 private symbols ignored", not any("_hidden" in s for s in cov["modules"]["big-b"]["unmentioned_symbols"]))
    (specs / "modules" / "big-b.md").write_text(spec("BIGB", "big-b", good_b.replace("`add` returns", "`small.add` returns")))
    run("coverage.py", str(specs), "--repo", str(repo), "--min-symbol", "0.5")
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
    aud = meta / "audit"
    aud.mkdir()
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
    js = [json.loads(l) for l in (ev / "audit" / "judge-sample.jsonl").read_text().splitlines()]
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
    cov_args = ("coverage.py", str(specs), "--repo", str(repo), "--min-file", "0", "--min-symbol", "0")
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
    (specs / "modules" / "big-a.md").write_text(spec("BIGA", "big-a", good_a))
    (specs / "modules" / "big-b.md").write_text(spec("BIGB", "big-b", good_b))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print(" -", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
