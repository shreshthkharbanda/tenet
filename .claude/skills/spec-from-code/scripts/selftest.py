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

    # L01: --include scopes; out-of-scope files stay as context
    rc, out = run("inventory.py", str(repo), "--out", str(meta / "inventory.json"), "--include", "pkg/big.py", "--include", "pkg/small.py")
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
    (meta / "reconcile" / "decisions-01.jsonl").write_text(json.dumps(
        {"row": 0, "verdict": "duplicate", "edits": [{"file": "modules/big-a.md", "id": "BIGA-001", "text": "a different rewrite"}]}) + "\n")
    before = (specs / "modules" / "big-a.md").read_text()
    rc, out = run("apply_claim_edits.py", str(specs))
    check("L35 conflicting edits are not applied and fail", rc == 1 and "CONFLICT" in out
          and (specs / "modules" / "big-a.md").read_text() == before, out)
    (meta / "reconcile" / "decisions-01.jsonl").unlink()

    # L36: ownership gate: cross-cutting restatement fails, pointers pass
    xc = ("---\nkind: config\nprefix: CFG\ncommit: " + head + "\nstatus: draft\n---\n# Config\n\n## Settings\n"
          "- [CFG-001] {confirmed} `pkg/small.py:1-2` `add` sums its arguments without checks.\n"
          "- [CFG-002] {confirmed} `pkg/small.py:1-2` `add` behavior is specified in [BIGB-001].\n\n## Precedence\nNone.\n")
    (specs / "03-config.md").write_text(xc)
    rc, out = run("check_ownership.py", str(specs), "--repo", str(repo), "--max-restated", "0.4")
    own_r = json.loads((meta / "ownership.json").read_text())
    check("L36 restating module lines without a pointer is counted", own_r["03-config.md"]["flagged"] == 1
          and own_r["03-config.md"]["ids"] == ["CFG-001"] and rc == 1, out)
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
    (meta / "probes").mkdir()
    (meta / "probes" / "big-a.jsonl").write_text("\n".join(json.dumps(p) for p in probes) + "\n")
    rc, out = run("score_probes.py", str(specs), "--assign-splits")
    rows = [json.loads(l) for l in (meta / "probes" / "big-a.jsonl").read_text().splitlines()]
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
        ad, jd = meta / "answers" / f"round-{rnd}", meta / "judgments" / f"round-{rnd}"
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
    val = json.loads((meta / "validation.json").read_text())
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
    val2 = json.loads((meta / "validation.json").read_text())
    lost = val2["rounds"]["1"]["big-a"]["holdout_agree"] - val2["modules"]["big-a"]["holdout_agree"]
    check("L11 regression by count", (val2["modules"]["big-a"]["status"] == "REGRESSION") == (lost >= 2), json.dumps(val2["modules"]))

    # L22: no-spec control round 0 feeds a control/lift column; never treated as a previous round
    ctl = tmp / "control"
    rc, out = run("snapshot_for_answerers.py", str(specs), "--out", str(ctl), "--questions-only")
    files = sorted(p.name for p in ctl.rglob("*") if p.is_file())
    check("L22 control snapshot holds questions only", files == ["big-a.questions.jsonl"], str(files))
    (meta / "judgments" / "round-0").mkdir(parents=True)
    (meta / "judgments" / "round-0" / "big-a.jsonl").write_text("\n".join(
        json.dumps({"id": r["id"], "verdict": "agree" if i < 5 else "gap"}) for i, r in enumerate(rows)) + "\n")
    rc, out = run("score_probes.py", str(specs), "--round", "0")
    check("L22 round 0 cannot be scored as a round", rc != 0, out)
    rc, out = run("score_probes.py", str(specs), "--round", "1", "--snapshot", str(snap))
    v1 = json.loads((meta / "validation.json").read_text())["modules"]["big-a"]
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
    js = [json.loads(l) for l in (aud / "judge-sample.jsonl").read_text().splitlines()]
    check("L22 judge sample is blind", js and all("verdict" not in r for r in js), str(js[:1]))

    # G5 + L03/L17: isolation checks with a specs dir not named "specs"; relative output paths resolve
    wr = meta / "worker-reports"
    wr.mkdir()
    (wr / "prober-big-a.json").write_text(json.dumps({"role": "prober", "module": "big-a", "outputs": [{"path": str(meta / "probes" / "big-a.jsonl")}],
                                                    "files_read": ["pkg/big.py", str(specs / "modules" / "big-a.md")]}))
    (wr / "answerer-big-a-round-1.json").write_text(json.dumps({"role": "answerer", "module": "big-a", "snapshot": str(snap),
                                                              "outputs": [{"path": str(meta / "answers" / "round-1" / "big-a.jsonl")}],
                                                              "files_read": [str(snap / "modules" / "big-a.md"), "pkg/big.py"]}))
    (wr / "extractor-big-b.json").write_text(json.dumps({"role": "extractor", "module": "big-b",
                                                       "outputs": [{"path": f"{specs.name}/modules/big-b.md", "claims": 2}],
                                                       "files_read": ["pkg/small.py"]}))
    (tmp / "reads.txt").write_text(str(repo / "pkg" / "small.py") + "\n")
    rc, out = run("write_report.py", "--specs", str(specs), "--role", "judge", "--module", "big-a", "--round", "1",
                  "--output", str(meta / "probes" / "big-a.jsonl"), "--read-from", str(tmp / "reads.txt"),
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

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print(" -", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
