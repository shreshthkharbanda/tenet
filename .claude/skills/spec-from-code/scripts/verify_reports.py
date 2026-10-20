#!/usr/bin/env python3
"""Gate G5: verify worker reports against the dispatch log, the filesystem, and (when available) the
workers' own transcripts.

Workers misreport (Rebuild Dossier, 2026): an agent's summary is a claim, the log is evidence, the files
are truth. A self-declared read list cannot prove isolation (L57: every isolation rule passed on forged
reports), so the checks run on three sources:
  1. Dispatch reconciliation. Every finished dispatch row needs the report its brief implies, under the
     role the orchestrator launched (a relabelled report is a missing one). Zero reports for a run that
     dispatched workers is a failure.
  2. Outputs. Reported outputs exist, are non-empty, were modified after the worker was launched, and
     their claim counts (computed by write_report.py) match what parses now within tolerance.
  3. Access. Per-role rules, checked on the self-reported read list and, with --transcripts, on every
     path the worker's tool calls actually touched (Read/Grep/Glob paths, paths in Bash commands after
     expanding variables set in the same command, and file paths printed by search commands).
     Spec text is recognized by its frontmatter wherever it lives (snapshots, rebuild copies).

Role rules (dispatch role wins over the report's):
  writers (surveyor, extractor, crosscut kinds, reconciler, pairjudge, reviser): nothing in the eval
      dir, answerer snapshots, or the control dir; extractors also no other module's spec
  prober: no spec text; in the eval dir only its own probe file
  answerer / control: everything under the snapshot that holds its rendered brief, nothing in the repo,
      the specs dir, or the eval dir beyond its own answers file
  judge, story-scorer: no spec text; judge-auditor: no spec text and no judgments
  story-reader: like an answerer, inside its story snapshot (story.md and questions.jsonl only)
  rebuilder: nothing outside its rebuild copy (the dir holding its brief), no test files
A finding judged harmless on evidence (e.g. an `ls` of a file that did not exist yet) is waived only by
a row in <eval dir>/g5-waivers.jsonl (never under the specs dir, which workers can write; match 12+
characters): {"report": "<report file>", "match": "<text in the error>", "reason":
"...", "evidence": "..."}. Waived findings print as WAIVED and stay in verify-report.json for the human.
Usage: verify_reports.py <specs_dir> --repo <root> [--transcripts DIR ...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from _common import eprint, eval_dir, expected_report, parse_claims, parse_frontmatter, read_json, reports_dirs, write_json

SOURCE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".scala",
              ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".ex", ".exs", ".sh", ".sql"}
SPEC_KINDS = {"module", "overview", "interfaces", "data", "config", "operations"}
WRITERS = {"surveyor", "extractor", "extractor-fix", "crosscut", "interfaces", "data", "config", "operations",
           "reconciler", "pairjudge", "reviser", "verifier", "narrator", "story-judge"}
XC_KINDS = {"interfaces", "data", "config", "operations"}
PATH_TOKEN = re.compile(r"(?<![\w$])(/[^\s'\"`;|&<>(){}]+)")
ASSIGN = re.compile(r"(?:^|[\s;&|(])(?:export\s+)?([A-Za-z_]\w*)=(\"[^\"]*\"|'[^']*'|[^\s;&|]+)")
SEARCH_CMD = re.compile(r"(?:^|[\s;&|(])(grep|rg|egrep|fgrep|find|ls|tree|ag)\b")


def resolve(p: str, repo: Path, specs: Path | None = None) -> Path:
    """Absolute paths as given; relative ones are tried against the repo, the specs dir's parent, and
    the specs dir, in that order (workers write 'specs/modules/x.md' meaning the specs tree)."""
    q = Path(p)
    if q.is_absolute():
        return Path(os.path.normpath(q))
    for base in [repo] + ([specs.parent, specs] if specs else []):
        cand = (base / q)
        if cand.exists():
            return cand.resolve()
    if specs and q.parts and q.parts[0] in ("specs", specs.name):
        return (specs / Path(*q.parts[1:])).resolve()
    return (repo / q).resolve()


def under(p: Path, root: Path) -> bool:
    try:
        Path(os.path.normpath(p)).relative_to(Path(os.path.normpath(root)))
        return True
    except ValueError:
        return False


_spec_cache: dict[Path, bool] = {}


def is_spec_text(p: Path) -> bool:
    """Spec text by content, not location: a .md whose frontmatter declares a spec kind."""
    if p.suffix != ".md":
        return False
    if p not in _spec_cache:
        try:
            fm, _ = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace")[:4000])
            _spec_cache[p] = fm.get("kind") in SPEC_KINDS
        except OSError:
            _spec_cache[p] = False
    return _spec_cache[p]


def transcript_for(agent: str, dirs: list[Path]) -> Path | None:
    for d in dirs:
        for name in (f"agent-{agent}.jsonl", f"{agent}.output", f"{agent}.jsonl"):
            if (d / name).exists():
                return d / name
    return None


def touched_paths(tfile: Path) -> list[tuple[str, str]]:
    """(how, absolute path) for every path the worker's tool calls touched."""
    uses, results = {}, {}
    for line in tfile.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                uses[b.get("id")] = (b.get("name"), b.get("input") or {})
            elif b.get("type") == "tool_result":
                c = b.get("content")
                if isinstance(c, list):
                    c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                results[b.get("tool_use_id")] = str(c or "")
    out: list[tuple[str, str]] = []
    for uid, (name, inp) in uses.items():
        res = results.get(uid, "")
        if name in ("Read", "NotebookRead"):
            out.append((name, str(inp.get("file_path") or inp.get("notebook_path") or "")))
        elif name in ("Grep", "Glob"):
            if inp.get("path"):
                out.append((name, str(inp["path"])))
            out += [(name + " result", ln.split(":", 1)[0].strip()) for ln in res.splitlines() if ln.startswith("/")]
        elif name == "Bash":
            cmd = str(inp.get("command", ""))
            env = {}
            for k, v in ASSIGN.findall(cmd):
                env[k] = v.strip("\"'")
            for _ in range(3):  # nested expansions (B=$A/x)
                for k, v in env.items():
                    env[k] = re.sub(r"\$\{?(\w+)\}?", lambda m: env.get(m.group(1), m.group(0)), v)
            exp = re.sub(r"\$\{?(\w+)\}?", lambda m: env.get(m.group(1), m.group(0)), cmd)
            cwd = None
            for m in re.finditer(r"(?:^|[\s;&|(])cd\s+(\S+)", exp):
                cwd = m.group(1).strip("\"'")
            out += [("Bash", t.rstrip(".,:)")) for t in PATH_TOKEN.findall(exp)]
            if cwd and cwd.startswith("/"):
                for t in re.findall(r"(?<![\w/$.-])((?:\.\./|[\w.-]+/)[\w./-]*)", exp):
                    out.append(("Bash(rel)", os.path.normpath(os.path.join(cwd, t))))
            if SEARCH_CMD.search(exp):
                for ln in res.splitlines():
                    head = ln.split(":", 1)[0].strip()
                    if head.startswith("/"):
                        out.append(("Bash result", head))
    # `wc -l` / grep -n style suffixes (path:25, path:10-20) are not part of the path
    return [(h, re.sub(r":\d+(?:-\d+)?$", "", p)) for h, p in out if p.startswith("/")]


OUTWARD_TOOLS = {"Artifact", "ArtifactComments", "ArtifactData", "SendMessage", "PushNotification", "SendUserFile",
                 "RemoteTrigger", "CronCreate", "ScheduleWakeup"}
OUTWARD_BASH = re.compile(r"(?:^|[\s;&|(])(git\s+(?:push|commit|tag)\b|gh\s+\w|curl\b[^|;&]*-X\s*(?:POST|PUT|PATCH|DELETE))")


def outward_actions(tfile: Path) -> list[str]:
    """Tool calls that act outside this machine or this run: publishing a page, an MCP connector call,
    messaging, scheduling, pushing or committing (L74: a narrator published its story as a page)."""
    out = []
    for line in tfile.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name, inp = str(b.get("name")), b.get("input") or {}
            if name == "Artifact" and inp.get("action") in ("read", "list", "quickstart"):
                continue  # reading a page changes nothing
            if name in OUTWARD_TOOLS or name.startswith("mcp__"):
                out.append(f"{name}({str(inp.get('action') or inp.get('file_path') or '')[:60]})")
            elif name == "Bash":
                m = OUTWARD_BASH.search(str(inp.get("command", "")))
                if m:
                    out.append(f"Bash({m.group(1)[:40]})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--transcripts", action="append", default=[],
                    help="dirs holding subagent transcripts (agent-<id>.jsonl or <id>.output)")
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    repo = Path(args.repo).resolve()
    ev = eval_dir(specs)
    skill_dir = Path(__file__).resolve().parent.parent
    tdirs = [Path(t).expanduser() for t in args.transcripts]
    errors: list[str] = []
    warnings: list[str] = []

    reports: dict[str, tuple[Path, dict]] = {}
    for d in reports_dirs(specs):
        for rf in sorted(d.glob("*.json")) if d.exists() else []:
            try:
                reports[rf.stem] = (rf, read_json(rf))
            except Exception as e:  # a malformed report is a finding about that worker, never a crash
                errors.append(f"{rf.name}: unreadable: {e}")
    log = specs / "_meta" / "dispatch.jsonl"
    rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()] if log.exists() else []

    # roots every rule refers to
    # answerer and story-reader snapshots hold held-out questions: no writer may touch them
    snapshots = {Path(r["brief"]).parent.parent for r in rows if r.get("role") in ("answerer", "story-reader") and r.get("brief")}
    controls = {Path(r["brief"]).parent for r in rows if r.get("role") == "control" and r.get("brief")}

    # 1. dispatch reconciliation
    if rows and not reports:
        errors.append("workers were dispatched but no worker reports exist")
    by_stem: dict[str, dict] = {}
    for r in rows:
        if not r.get("brief") or not Path(r["brief"]).suffix == ".md":
            warnings.append(f"dispatch row for agent {r.get('agent')} ({r.get('role')}) names no rendered brief; "
                            f"its report cannot be reconciled")
            continue
        stem = expected_report(Path(r["brief"]))
        by_stem[stem] = r  # the latest launch of a brief wins
    for stem, r in by_stem.items():
        if r.get("status") == "running":
            warnings.append(f"{stem}: still running (agent {r.get('agent')})")
        elif stem.startswith("pairjudge-") and (specs / "_meta" / "reconcile" / f"decisions-{stem.split('-', 1)[1]}.jsonl").exists():
            continue  # a pair judge's decision file is its proof of completion
        elif r.get("status") in ("ok", "done") and stem not in reports:
            errors.append(f"{stem}: dispatched as {r.get('role')} (agent {r.get('agent')}) and finished, but its "
                          f"report is missing (or was written under another role/module)")
    if rows:
        for stem in reports:
            if stem not in by_stem and not stem.startswith("pairjudge"):
                warnings.append(f"{stem}.json: no dispatch row launched this report's brief")

    unchecked = 0
    for stem, (rf, r) in sorted(reports.items()):
        missing = [k for k in ("role", "module", "outputs", "files_read") if k not in r]
        if missing:
            errors.append(f"{rf.name}: report lacks {missing}; write reports with scripts/write_report.py")
        drow = by_stem.get(stem)
        role = (drow or {}).get("role") or r.get("role", "?")
        if role == "crosscut" or role in XC_KINDS:
            role = "crosscut"
        module = r.get("module", "?")
        launched = None
        if drow and drow.get("launched"):
            try:
                launched = datetime.strptime(drow["launched"], "%Y-%m-%dT%H:%M:%S").timestamp()
            except ValueError:
                launched = None

        # 2. outputs
        outs = r.get("outputs", [])
        if not isinstance(outs, list):
            errors.append(f"{rf.name}: 'outputs' must be a list")
            outs = []
        for o in outs:
            o = {"path": o} if isinstance(o, str) else o
            if not isinstance(o, dict) or "path" not in o:
                errors.append(f"{rf.name}: malformed output entry {str(o)[:80]}")
                continue
            fp = resolve(o["path"], repo, specs)
            if not fp.exists() or (fp.is_file() and fp.stat().st_size == 0):
                errors.append(f"{rf.name}: reported output {o['path']} missing or empty")
                continue
            mt = o.get("mtime", fp.stat().st_mtime if fp.is_file() else None)
            if launched and mt and mt < launched - 120:
                errors.append(f"{rf.name}: output {o['path']} was last modified before the worker was launched")
            if fp.suffix == ".md" and fp.is_file():
                actual = len(parse_claims(parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))[1]))
                for key in ("claims_reported", "claims"):
                    if key in o and abs(actual - int(o[key])) > max(2, 0.10 * max(actual, int(o[key]))):
                        errors.append(f"{rf.name}: {key} {o[key]} for {o['path']} but {actual} parse")
                        break

        # 3. access: self-reported reads plus transcript evidence
        fr = r.get("files_read", [])
        if not isinstance(fr, list):
            errors.append(f"{rf.name}: 'files_read' must be a list")
            fr = []
        accesses = [("reported", resolve(str(x), repo, specs)) for x in fr]
        if not fr and role not in ("pairjudge",):
            errors.append(f"{rf.name}: no files_read listed; every worker must list what it read")
        tfile = transcript_for(drow["agent"], tdirs) if drow and drow.get("agent") and tdirs else None
        if tfile:
            accesses += [(how, Path(os.path.normpath(p))) for how, p in touched_paths(tfile)]
            acts = outward_actions(tfile)
            if acts:
                errors.append(f"{rf.name}: worker acted outside this run (published, messaged, pushed or called a "
                              f"connector); workers only write files: {sorted(set(acts))[:5]}")
        elif tdirs:
            unchecked += 1

        # a worker's own outputs and report are always reachable; a bare directory token (cd, mkdir, --specs)
        # that is an ancestor of one is not a read. Search results are concrete files and get no such pass.
        own = [d / rf.name for d in reports_dirs(specs)] + [resolve(o["path"] if isinstance(o, dict) else str(o), repo, specs)
                                                            for o in outs if isinstance(o, (dict, str)) and (not isinstance(o, dict) or "path" in o)]
        if drow and drow.get("brief"):
            own.append(Path(drow["brief"]))  # its own brief
        own += [Path(x) for x in r.get("legacy_outputs", [])]  # where outputs were before a layout migration
        # a declared output may never whitelist a directory, a protected root or anything above one, and a
        # writer's declared output may not sit in the eval dir (L71: declaring $EVAL or "/" as an output
        # made the own-output pass bless every read under it)
        protected = [ev, specs, repo, *snapshots, *controls]
        own = [o for o in own if o.suffix and not any(under(pr, o) for pr in protected)
               and not (role in WRITERS and under(o, ev))]

        def own_or_ancestor(how: str, p: Path, extra: list) -> bool:
            roots = own + extra
            return any(under(p, a) for a in roots) or (("result" not in how or p.is_dir()) and any(under(a, p) for a in roots))

        def flag(why: str, hits: list) -> None:
            hits = [(h, p) for h, p in hits if not own_or_ancestor(h, p, [])]
            if hits:
                shown = sorted({f"{h}:{p}" for h, p in hits})[:5]
                errors.append(f"{rf.name}: {why}: {shown}")

        flag("worker touched the G5 waivers file (only the orchestrator writes waivers)",
             [(h, p) for h, p in accesses if p.name == "g5-waivers.jsonl"])
        brief_home = Path(drow["brief"]).parent if drow and drow.get("brief") else None
        if brief_home and brief_home == specs / "_meta" / "briefs":
            brief_home = None  # a brief rendered before L53 placement: fall back to the declared root
        if role in WRITERS:
            # the legacy in-specs locations stay forbidden, so older runs are judged by the same rule
            forbidden = [ev, *snapshots, *controls] + [specs / "_meta" / x for x in (
                "probes", "answers", "judgments", "validation.json", "validation-report.md", "probe-corrections.jsonl")]
            flag(f"{role} touched the eval dir or an answerer snapshot (held-out answers reachable)",
                 [(h, p) for h, p in accesses if any(under(p, f) for f in forbidden)])
            if role in ("extractor", "extractor-fix"):
                flag(f"extractor for {module} read another module's spec (independence broken)",
                     [(h, p) for h, p in accesses if under(p, specs / "modules") and p.suffix == ".md" and p.stem != module])
        elif role == "prober":
            own_probe = ev / "probes" / f"{module}.jsonl"
            flag("prober read spec text (blindness broken)",
                 [(h, p) for h, p in accesses if p.is_file() and is_spec_text(p)
                  or under(p, specs / "modules") or (under(p, specs) and p.name.startswith("0") and p.suffix == ".md")])
            flag("prober touched the eval dir beyond its own probe file",
                 [(h, p) for h, p in accesses if under(p, ev) and p != own_probe and not under(p, ev / "worker-reports")
                  and p != ev and p != ev / "probes"])
        elif role in ("answerer", "control", "story-reader"):
            home = (brief_home.parent if role != "control" else brief_home) if brief_home else None
            declared = resolve(r["snapshot"], repo) if r.get("snapshot") else None
            if role != "control" and not r.get("snapshot"):
                errors.append(f"{rf.name}: answerer report lacks 'snapshot'")
            if home and declared and declared != home:
                errors.append(f"{rf.name}: declared snapshot {declared} is not the dir holding its brief ({home})")
            root = home or declared
            if root is None:
                errors.append(f"{rf.name}: cannot tell which snapshot this {role} was given (no dispatch row)")
            else:
                if under(specs, root) or under(repo, root) or under(root, repo) or under(root, specs):
                    errors.append(f"{rf.name}: snapshot {root} overlaps the specs dir or the repo")
                leaked = [str(x) for x in root.rglob("*") if x.suffix in SOURCE_EXT] if root.exists() else []
                if leaked:
                    errors.append(f"{rf.name}: snapshot contains source files: {leaked[:5]}")
                own_answers = ev / "answers"
                allowed = [root, own_answers, ev / "worker-reports", skill_dir / "scripts"]
                flag(f"{role} read outside its snapshot (isolation broken)",
                     [(h, p) for h, p in accesses if not own_or_ancestor(h, p, allowed)
                      and (under(p, repo) or under(p, specs) or under(p, ev) or (h == "reported"))])
        elif role in ("judge", "judge-auditor", "story-scorer"):
            flag(f"{role} read spec text (judges compare answers with code, not with the spec)",
                 [(h, p) for h, p in accesses if (p.is_file() and is_spec_text(p)) or under(p, specs / "modules")])
            if role == "judge":
                rnd = r.get("round")
                flag("judge read another round's judgments or answers (verdicts must be independent per round)",
                     [(h, p) for h, p in accesses if any(under(p, ev / k) for k in ("judgments", "answers"))
                      and rnd is not None and f"round-{rnd}" not in p.parts
                      and p.suffix])  # a file; listing a directory shows names, not verdicts
            if role == "judge-auditor":
                flag("judge auditor read the original judgments (blindness broken)",
                     [(h, p) for h, p in accesses if under(p, ev / "judgments")])
        elif role == "reader":
            flag("reader read source or the eval dir (it must explain the system from the spec alone)",
                 [(h, p) for h, p in accesses if (under(p, repo) or under(p, ev)) and not under(p, skill_dir)])
        elif role == "rebuilder":
            root = brief_home or (resolve(r["snapshot"], repo) if r.get("snapshot") else None)
            if root is None:
                errors.append(f"{rf.name}: rebuilder report lacks 'snapshot' (its rebuild copy)")
            else:
                if r.get("snapshot") and brief_home and resolve(r["snapshot"], repo) != brief_home:
                    errors.append(f"{rf.name}: declared copy {r['snapshot']} is not the dir holding its brief ({brief_home})")
                flag("rebuilder read outside its copy (original code reachable)",
                     [(h, p) for h, p in accesses if (under(p, repo) or under(p, specs) or under(p, ev) or h == "reported")
                      and not own_or_ancestor(h, p, [root, skill_dir])])
                flag("rebuilder read test source (expected values leak past the spec)",
                     [(h, p) for h, p in accesses if under(p, root) and h in ("reported", "Read", "Bash")
                      and ("/tests/" in str(p) or "/test/" in str(p) or p.name.startswith("test_")
                           or p.name.endswith(("_test.py", ".test.ts", "Test.java")))])
    if tdirs and unchecked:
        warnings.append(f"{unchecked} reports had no transcript; their isolation rests on the self-reported read list")
    if not tdirs and rows:
        warnings.append("no --transcripts given: isolation rests on self-reported read lists (pass the subagent "
                        "transcript dir to check what workers actually opened)")
    wf = ev / "g5-waivers.jsonl"  # outside the specs dir: a worker cannot waive its own findings (L71)
    waivers = [json.loads(l) for l in wf.read_text().splitlines() if l.strip()] if wf.exists() else []
    waived = []
    for w in waivers:
        if not (w.get("reason") and w.get("evidence")):
            errors.append(f"g5-waivers.jsonl: waiver for {w.get('report')} lacks a reason or evidence")
        if len(str(w.get("match", ""))) < 12:
            errors.append(f"g5-waivers.jsonl: waiver for {w.get('report')} has a match shorter than 12 characters; "
                          f"a waiver must name the specific finding it covers")
    if (specs / "_meta" / "g5-waivers.jsonl").exists():
        errors.append("_meta/g5-waivers.jsonl exists inside the specs dir, where workers can write; waivers are read "
                      "only from the eval dir")
    for e in list(errors):
        w = next((w for w in waivers if w.get("reason") and w.get("evidence") and len(str(w.get("match", ""))) >= 12
                  and e.startswith(str(w.get("report")) + ":")
                  and str(w.get("match", "")) in e), None)
        if w:
            errors.remove(e)
            waived.append(f"{e} -- WAIVED: {w['reason']} ({w['evidence']})")
    write_json(specs / "_meta" / "verify-report.json", {"checked": len(reports), "errors": errors, "warnings": warnings,
                                                       "waived": waived})
    for w in waived:
        eprint("WAIVED:", w)
    for w in warnings[:50]:
        eprint("WARN:", w)
    for e in errors:
        eprint("ERROR:", e)
    eprint(f"verify: {len(reports)} worker reports, {len(errors)} discrepancies")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
