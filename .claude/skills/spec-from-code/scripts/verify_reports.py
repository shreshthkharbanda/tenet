#!/usr/bin/env python3
"""Gate G5: three-level verification of worker self-reports against the filesystem.

Workers misreport (Rebuild Dossier, 2026): an agent's summary is a claim, the log is
evidence, the files are truth. Each worker writes _meta/worker-reports/<role>-<module>[-round-N].json:
  {"role": "...", "module": "...", "outputs": [{"path": "...", "claims": N}],
   "files_read": [...], "snapshot": "<answerers only: the snapshot dir>", "notes": "..."}

Isolation rules are checked against the real specs directory (whatever it is named) and the
answerer's declared snapshot, never against a literal directory name:
  - answerer: every read resolves inside its snapshot; the snapshot contains no source files
  - prober: no read of any spec text (modules/, 0*.md, INDEX.md) or of answers/judgments
  - extractor / reviser: no read of another module's spec
  - every role: reported outputs exist, are non-empty, and claim counts match what parses
Usage: verify_reports.py <specs_dir> --repo <root>
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import eprint, parse_claims, parse_frontmatter, read_json, write_json

SOURCE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".scala",
              ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".ex", ".exs", ".sh", ".sql"}
PROBER_ALLOWED_META = {"modules.json", "survey.md", "shards-report.json", "inventory.json"}


def resolve(p: str, repo: Path, specs: Path | None = None) -> Path:
    """Absolute paths as given; relative ones are tried against the repo, the specs dir's parent, and
    the specs dir, in that order (workers write 'specs/modules/x.md' meaning the specs tree)."""
    q = Path(p)
    if q.is_absolute():
        return q.resolve()
    for base in [repo] + ([specs.parent, specs] if specs else []):
        cand = (base / q)
        if cand.exists():
            return cand.resolve()
    if specs and q.parts and q.parts[0] in ("specs", specs.name):
        return (specs / Path(*q.parts[1:])).resolve()
    return (repo / q).resolve()


def under(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    repo = Path(args.repo).resolve()
    rdir = specs / "_meta" / "worker-reports"
    if not rdir.exists():
        eprint("no worker reports found")
        return 1
    errors: list[str] = []
    checked = 0
    for rf in sorted(rdir.glob("*.json")):
        try:
            r = read_json(rf)
        except Exception as e:
            errors.append(f"{rf.name}: unreadable: {e}")
            continue
        checked += 1
        missing = [k for k in ("role", "module", "outputs", "files_read") if k not in r]
        if missing:
            errors.append(f"{rf.name}: report lacks {missing}; write reports with scripts/write_report.py")
        role = r.get("role", "?")
        module = r.get("module", "?")
        # Schema tolerance: a malformed report is a finding about that worker, never a crash of the gate.
        outs = r.get("outputs", [])
        if not isinstance(outs, list):
            errors.append(f"{rf.name}: 'outputs' must be a list")
            outs = []
        norm = []
        for o in outs:
            if isinstance(o, str):
                norm.append({"path": o})
            elif isinstance(o, dict) and "path" in o:
                norm.append(o)
            else:
                errors.append(f"{rf.name}: malformed output entry {str(o)[:80]}")
        for o in norm:
            fp = resolve(o.get("path", ""), repo, specs)
            if not fp.exists() or (fp.is_file() and fp.stat().st_size == 0):
                errors.append(f"{rf.name}: reported output {o.get('path')} missing or empty")
                continue
            if "claims" in o and fp.suffix == ".md":
                _, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
                actual = len(parse_claims(body))
                rep = int(o["claims"])
                if abs(actual - rep) > max(2, 0.10 * max(actual, rep)):
                    errors.append(f"{rf.name}: reported {rep} claims in {o.get('path')} but {actual} parse")
        fr = r.get("files_read", [])
        if not isinstance(fr, list):
            errors.append(f"{rf.name}: 'files_read' must be a list")
            fr = []
        reads = [resolve(str(x), repo, specs) for x in fr]
        if not reads and role not in ("judge",):
            errors.append(f"{rf.name}: no files_read listed; every worker must list what it read")
        if role == "answerer":
            snap = r.get("snapshot")
            if not snap:
                errors.append(f"{rf.name}: answerer report lacks 'snapshot'")
            else:
                sroot = resolve(snap, repo)
                bad = [str(x) for x in reads if not under(x, sroot)]
                if bad:
                    errors.append(f"{rf.name}: answerer read outside its snapshot (isolation broken): {bad[:5]}")
                if under(sroot, repo):
                    errors.append(f"{rf.name}: snapshot {sroot} is inside the repo; answerers must not be able to reach source by relative path")
                leaked = [str(x) for x in sroot.rglob("*") if x.suffix in SOURCE_EXT] if sroot.exists() else []
                if leaked:
                    errors.append(f"{rf.name}: snapshot contains source files: {leaked[:5]}")
        if role == "prober":
            for x in reads:
                if not under(x, specs):
                    continue
                rel = x.relative_to(specs)
                ok = (rel.parts[:1] == ("_meta",) and (
                    (len(rel.parts) == 2 and rel.parts[1] in PROBER_ALLOWED_META)
                    or rel.parts[1:2] == ("briefs",)
                    or (rel.parts[1:2] == ("probes",) and rel.stem == module)))
                if not ok:
                    errors.append(f"{rf.name}: prober read {rel} (blindness broken: probers may not read spec text)")
        if role in ("extractor", "reviser"):
            for x in reads:
                if under(x, specs / "modules") and x.stem != module:
                    errors.append(f"{rf.name}: {role} for {module} read another module's spec {x.name} (independence broken)")
    write_json(specs / "_meta" / "verify-report.json", {"checked": checked, "errors": errors})
    for e in errors:
        eprint("ERROR:", e)
    eprint(f"verify: {checked} worker reports, {len(errors)} discrepancies")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
