#!/usr/bin/env python3
"""Render worker briefs from references/briefs.md into files, with every placeholder filled
from modules.json, the shard plan, and the inventory. Refuses to write a brief with a
placeholder left. The Agent prompt is then one line: "Your complete instructions are in
<path>. Read that file first and follow it exactly."

Why files: at tier M/L the orchestrator would otherwise paste dozens of multi-kilobyte briefs
into its own context, and hand-filled placeholders drift (wrong module's file list, stale
round number). One renderer, one source of truth.

Usage:
  render_briefs.py --role surveyor
  render_briefs.py --role extractor|prober|reviser|rebuilder --module ID [--module ID ...] | --all-modules
  render_briefs.py --role crosscut --kind interfaces|data|config|operations [--kind ...]
  render_briefs.py --role reconciler
  render_briefs.py --role answerer --round N --snapshot DIR (--module ID ... | --all-modules)
  render_briefs.py --role judge --round N (--module ID ... | --all-modules)
Common: --specs DIR --repo DIR --scratch DIR [--n-probes 25] [--test-cmd CMD] [--scope-note TEXT]
Prints one line per brief: <role> <module> <path>.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from _common import build_ownership, eprint, git_head, glob_to_regex, read_json, scope_label

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
XC = {"interfaces": ("01-interfaces.md", "IF"), "data": ("02-data.md", "DATA"),
      "config": ("03-config.md", "CFG"), "operations": ("04-operations.md", "OPS")}


def load_blocks() -> tuple[dict, dict]:
    text = "\n".join((SKILL_DIR / "references" / f).read_text(encoding="utf-8") for f in ("briefs.md", "audit.md"))
    blocks, focus = {}, {}
    for kind, name, body in re.findall(r"<!-- (brief|focus):(\w+) -->\s*\n```[^\n]*\n(.*?)\n```", text, re.S):
        (blocks if kind == "brief" else focus)[name] = body
    return blocks, focus


def fill(template: str, values: dict, must_use: tuple = ()) -> str:
    unused = [k for k in must_use if "{{" + k + "}}" not in template]
    if unused:
        raise SystemExit(f"this role's template does not use {unused}, so the value you passed would be silently "
                         f"dropped; add the placeholder to the brief or stop passing the option")
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", str(v))
    left = sorted(set(re.findall(r"\{\{([A-Z_]+)\}\}", out)))
    if left:
        raise SystemExit(f"unfilled placeholders {left}; pass the missing option (see --help)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--all-modules", action="store_true")
    ap.add_argument("--kind", action="append", default=[])
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--specs", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--n-probes", type=int, default=25)
    ap.add_argument("--test-cmd", default="(see 04-operations.md; if absent, find the project's test command)")
    ap.add_argument("--scope-note", default="")
    ap.add_argument("--refresh-refs", action="store_true", help="re-copy references into _meta/skill-refs")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="extra placeholder values (audit roles: SAMPLE_FILE, CONTROL_DIR, READER_SCENARIO)")
    args = ap.parse_args()
    specs, repo, scratch = Path(args.specs).resolve(), Path(args.repo).resolve(), Path(args.scratch).resolve()
    blocks, focus = load_blocks()
    role = args.role
    if role not in blocks:
        raise SystemExit(f"unknown role {role}; known: {sorted(blocks)}")
    meta = specs / "_meta"
    mods = read_json(meta / "modules.json") if (meta / "modules.json").exists() else {"modules": []}
    inv = read_json(meta / "inventory.json")
    commit = mods.get("commit") or git_head(repo) or "unknown"
    base = {"REPO": repo, "SPECS": specs, "SKILL_DIR": SKILL_DIR, "COMMIT": commit, "SCRATCH": scratch,
            "ROUND": args.round, "N_PROBES": args.n_probes, "TEST_CMD": args.test_cmd}
    # Freeze the references workers read, once per run: editing the skill mid-run must not change the
    # rules under workers already running. --refresh-refs re-copies deliberately.
    refs = meta / "skill-refs"
    if args.refresh_refs or not refs.exists():
        refs.mkdir(parents=True, exist_ok=True)
        for name in ("templates.md", "implicit-decisions.md"):
            (refs / name).write_text((SKILL_DIR / "references" / name).read_text(encoding="utf-8"), encoding="utf-8")
    base["REFS"] = refs
    env_md = meta / "env.md"
    base["RUN_ENV"] = (env_md.read_text(encoding="utf-8").strip() if env_md.exists() else
                       "no verified way to run this project's code was recorded (_meta/env.md is missing); "
                       "work from reading, and mark execution-dependent facts {inferred}.")
    for kv in args.set:
        if "=" not in kv:
            raise SystemExit(f"--set expects KEY=VALUE, got {kv!r}")
        k, v = kv.split("=", 1)
        base[k.strip()] = v
    includes = inv["summary"].get("includes") or []
    default_scope = ("the whole repository" if not includes else
                     "only files matching " + ", ".join(includes) + "; everything else is context you may read but do not specify")
    out_dir = meta / "briefs"
    rendered = []
    must = ("SCOPE_NOTE",) if args.scope_note else ()

    if role == "pairjudge":
        n = sum(1 for l in (meta / "overlaps.jsonl").read_text().splitlines() if l.strip())
        size = int(next((kv.split("=", 1)[1] for kv in args.set if kv.startswith("SLICE_SIZE=")), "60"))
        for k, lo in enumerate(range(0, n, size)):
            hi = min(n, lo + size)
            vals = base | {"SLICE": f"{lo}-{hi}", "SLICE_NAME": f"{k:02d}"}
            rendered.append((role, f"slice-{k:02d}", out_dir / f"pairjudge-{k:02d}.md", fill(blocks[role], vals, must)))
        (meta / "reconcile").mkdir(parents=True, exist_ok=True)
    elif role in ("surveyor", "reconciler", "control", "judge-auditor", "redteam", "reader", "lifecycle-checker"):
        name = f"audit-{role}.md" if role not in ("surveyor", "reconciler") else f"{role}.md"
        dest = out_dir / name
        if role == "control":  # the control may read only its own directory, so its brief lives there
            dest = Path(base["CONTROL_DIR"]).resolve() / "_brief.md" if "CONTROL_DIR" in base else dest
        rendered.append((role, "all", dest, fill(blocks[role], base | {"SCOPE_NOTE": args.scope_note or default_scope}, must)))
    elif role == "crosscut":
        if not args.kind:
            raise SystemExit("--kind required for crosscut")
        for k in args.kind:
            f, pfx = XC[k]
            vals = base | {"XC_KIND": k, "XC_FILE": f, "XC_PREFIX": pfx, "XC_FOCUS": focus[k],
                           "SCOPE_NOTE": args.scope_note or default_scope}
            rendered.append((role, k, out_dir / f"{k}.md", fill(blocks["crosscut"], vals, must)))
    else:
        own = build_ownership(mods, inv["files"], repo)
        ids = [m["id"] for m in mods["modules"]] if args.all_modules else args.module
        if not ids:
            raise SystemExit("--module or --all-modules required")
        tests = [f["path"] for f in inv["files"] if f.get("is_test")]
        for mid in ids:
            m = next((x for x in mods["modules"] if x["id"] == mid), None)
            if not m:
                raise SystemExit(f"unknown module {mid}")
            items = own["assign"].get(mid, [])
            files = "\n".join(f"  {scope_label(i)}   ({i['loc']} LOC)" for i in items)
            ranged = [i for i in items if not i.get("whole")]
            note = args.scope_note
            if ranged:
                note = (note + "\n" if note else "") + (
                    "Some of your scope is a LINE RANGE of a larger file (path:START-END above). Specify only behavior "
                    "implemented inside your ranges. You may read the rest of the file for context (constructor state, "
                    "helpers you call); describe what your code relies on from outside the range as {inferred} with a "
                    "ref, and do not specify it in full: another extractor owns it.")
            tg = [glob_to_regex(g) for g in m.get("test_globs", [])]
            tfiles = [t for t in tests if any(rx.match(t) for rx in tg)]
            if not tfiles:
                # heuristic: tests whose path mentions the module id or a scoped file stem
                stems = {Path(i["path"]).stem for i in items if Path(i["path"]).stem not in ("__init__", "utils", "common")}
                tfiles = [t for t in tests if any(s_ and s_ in t for s_ in stems)][:40]
            tlist = "\n".join(f"  {t}" for t in tfiles) or "  (none mapped: grep the test tree for this module's public symbols)"
            vals = base | {"MODULE_ID": mid, "PREFIX": m["prefix"], "MODULE_NAME": m.get("name", mid),
                           "GLOBS": ", ".join(m.get("globs", [])), "FILES": files, "TEST_FILES": tlist,
                           "SCOPE_NOTE": note}
            if role == "answerer":
                if not args.snapshot:
                    raise SystemExit("--snapshot required for answerer")
                snap = Path(args.snapshot).resolve()
                vals["SPEC_SNAPSHOT"] = snap
                path = snap / "_briefs" / f"answerer-{mid}-round-{args.round}.md"
            elif role in ("judge", "reviser"):
                path = out_dir / f"{role}-{mid}-round-{args.round}.md"
            elif role in ("falsifier", "omission"):
                path = out_dir / f"audit-{role}-{mid}.md"
            else:
                path = out_dir / f"{role}-{mid}.md"
            if role == "rebuilder":
                vals["SCRATCH"] = scratch / f"rebuild-{mid}"
            rendered.append((role, mid, path, fill(blocks[role], vals, must)))
    for r, mid, path, text in rendered:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"{r}\t{mid}\t{path}")
    eprint(f"rendered {len(rendered)} brief(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
