#!/usr/bin/env python3
"""Mechanical rebuild harness. Two subcommands, both run by the orchestrator (never the Rebuilder).

setup: copy the repo (no .git) to <scratch>/rebuild-<module>/, copy spec TEXT only (no probes,
       answers, judgments: those hold code-derived truths), run the test command on the untouched
       copy (baseline JUnit), remove the module's files or line ranges (ranges are replaced by one
       marker comment at the same indentation), then run the tests again (deletion check).
       If deleting the module breaks no baseline-passing test, the harness is not exercising the
       copy (e.g. the package resolves to the original checkout) or no test covers the module:
       the rebuild could not tell a good spec from a bad one, so setup fails.
score: run the tests on the rebuilt copy and score against the baseline with score_rebuild.py.

The test command must contain {junit}, replaced by the JUnit XML output path, e.g.
  "python -m pytest tests/unit/router_utils -q -p no:cacheprovider --junitxml={junit}"

Usage:
  prepare_rebuild.py setup --specs DIR --repo DIR --scratch DIR --module ID --test-cmd CMD [--python-pkg NAME]
  prepare_rebuild.py score --specs DIR --scratch DIR --module ID --test-cmd CMD
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from _common import build_ownership, eprint, read_json, write_json

HERE = Path(__file__).resolve().parent
COPY_IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
                                     ".pytest_cache", ".ruff_cache", "target", "dist", "build")


def run_tests(cwd: Path, cmd: str, junit: Path, timeout: int) -> int:
    junit.parent.mkdir(parents=True, exist_ok=True)
    if junit.exists():
        junit.unlink()
    full = cmd.replace("{junit}", str(junit))
    eprint(f"$ (cd {cwd} && {full})")
    try:
        p = subprocess.run(full, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        (junit.parent / (junit.stem + ".log")).write_text(p.stdout[-20000:] + "\n" + p.stderr[-20000:])
        return p.returncode
    except subprocess.TimeoutExpired:
        eprint("test command timed out")
        return 124


def score(base: Path, after: Path, module: str, out: Path) -> dict:
    subprocess.run([sys.executable, str(HERE / "score_rebuild.py"), "--baseline", str(base), "--after", str(after),
                    "--module", module, "--out", str(out)], check=True)
    return read_json(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["setup", "score"])
    ap.add_argument("--specs", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--test-cmd", required=True)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--python-pkg", default=None, help="if set, verify `import PKG` resolves inside the copy")
    ap.add_argument("--python-exe", default="python3", help="interpreter the test command uses (for --python-pkg)")
    args = ap.parse_args()
    if "{junit}" not in args.test_cmd:
        raise SystemExit("--test-cmd must contain {junit} (the JUnit XML output path)")
    specs = Path(args.specs).resolve()
    work = Path(args.scratch).resolve() / f"rebuild-{args.module}"
    rdir = specs / "_meta" / "rebuild"
    rdir.mkdir(parents=True, exist_ok=True)
    junit_dir = Path(args.scratch).resolve() / f"rebuild-{args.module}-junit"

    if args.cmd == "setup":
        repo = Path(args.repo).resolve()
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(repo, work, ignore=COPY_IGNORE, symlinks=True)
        # spec text only
        if (work / specs.name).exists():
            shutil.rmtree(work / specs.name)
        dst = work / "specs"
        for f in specs.rglob("*.md"):
            rel = f.relative_to(specs)
            if rel.parts[0] == "_meta" and not (len(rel.parts) == 2 and rel.name in ("gaps.md", "questions.md")):
                continue
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / rel)
        (dst / "_meta").mkdir(parents=True, exist_ok=True)
        shutil.copy2(specs / "_meta" / "modules.json", dst / "_meta" / "modules.json")
        if args.python_pkg:
            p = subprocess.run([args.python_exe, "-c",
                                f"import {args.python_pkg},sys; print({args.python_pkg}.__file__)"],
                               cwd=work, capture_output=True, text=True)
            where = p.stdout.strip()
            if not where.startswith(str(work)):
                raise SystemExit(f"`import {args.python_pkg}` resolves to {where or p.stderr.strip()[:200]}, not the copy; "
                                 f"fix the environment (PYTHONPATH={work}) before rebuilding")
        rc = run_tests(work, args.test_cmd, junit_dir / "baseline.xml", args.timeout)
        eprint(f"baseline exit {rc}")
        inv = read_json(specs / "_meta" / "inventory.json")
        mods = read_json(specs / "_meta" / "modules.json")
        own = build_ownership(mods, inv["files"], Path(args.repo).resolve())
        items = own["assign"].get(args.module, [])
        if not items:
            raise SystemExit(f"module {args.module} owns nothing")
        removed = []
        by_path: dict[str, list] = {}
        for it in items:
            by_path.setdefault(it["path"], []).append(it)
        for path, its in by_path.items():
            fp = work / path
            if all(i.get("whole") for i in its):
                fp.unlink()
                removed.append({"path": path, "whole": True})
                continue
            lines = fp.read_text(encoding="utf-8").splitlines(keepends=True)
            for it in sorted(its, key=lambda i: -i["start"]):
                a, b = it["start"], it["end"]
                first = lines[a - 1] if a - 1 < len(lines) else ""
                indent = first[: len(first) - len(first.lstrip())]
                marker = f"{indent}# REBUILD-MARKER {args.module} lines {a}-{b}: implement modules/{args.module}.md here\n"
                lines[a - 1:b] = [marker]
                removed.append({"path": path, "start": a, "end": b, "marker": marker.strip()})
            fp.write_text("".join(lines), encoding="utf-8")
        rc2 = run_tests(work, args.test_cmd, junit_dir / "deleted.xml", args.timeout)
        dele = score(junit_dir / "baseline.xml", junit_dir / "deleted.xml", args.module, rdir / f"{args.module}.deletion.json")
        manifest = {"module": args.module, "workdir": str(work), "removed": removed, "baseline_exit": rc,
                    "deleted_exit": rc2, "baseline_passing": dele["baseline_passing"],
                    "passing_after_deletion": dele["still_passing"],
                    "deletion_drop": dele["baseline_passing"] - dele["still_passing"]}
        write_json(rdir / f"{args.module}.setup.json", manifest)
        if manifest["deletion_drop"] == 0:
            raise SystemExit("deleting the module broke no baseline-passing test: the tests do not exercise this copy "
                             "or do not cover this module; pick another module or another test command")
        eprint(f"setup ok: {manifest['deletion_drop']} baseline-passing tests fail with the module removed; "
               f"rebuilder works in {work}")
        return 0

    run_tests(work, args.test_cmd, junit_dir / "after.xml", args.timeout)
    res = score(junit_dir / "baseline.xml", junit_dir / "after.xml", args.module, rdir / f"{args.module}.score.json")
    setup = read_json(rdir / f"{args.module}.setup.json")
    drop = setup["deletion_drop"]
    recovered = res["still_passing"] - setup["passing_after_deletion"]
    res["deletion_drop"] = drop
    res["recovered"] = recovered
    res["recovery_rate"] = round(recovered / drop, 4) if drop else None
    write_json(rdir / f"{args.module}.score.json", res)
    eprint(f"rebuild {args.module}: recovered {recovered}/{drop} tests broken by deletion "
           f"({res['recovery_rate']:.0%}); overall {res['still_passing']}/{res['baseline_passing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
