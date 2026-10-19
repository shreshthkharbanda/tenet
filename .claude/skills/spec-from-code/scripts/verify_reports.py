#!/usr/bin/env python3
"""Gate G5: three-level verification of worker self-reports against the filesystem.

Workers misreport (Rebuild Dossier, 2026): an agent's summary is a claim, the log is
evidence, the files are truth. Each worker writes _meta/worker-reports/<role>-<module>[-roundN].json:
  {"role": "...", "module": "...", "outputs": [{"path": "...", "claims": N}], "files_read": [...], "notes": "..."}

Checks: every reported output exists and is non-empty; reported claim counts match parsed
counts within 10%; answerers read only the specs directory; probers read no spec files.
Usage: verify_reports.py <specs_dir> --repo <root>
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import eprint, parse_claims, parse_frontmatter, read_json, write_json


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
        role = r.get("role", "?")
        for o in r.get("outputs", []):
            p = o.get("path", "")
            fp = (repo / p) if not Path(p).is_absolute() else Path(p)
            if not fp.exists() or fp.stat().st_size == 0:
                errors.append(f"{rf.name}: reported output {p} missing or empty")
                continue
            if "claims" in o and fp.suffix == ".md":
                _, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
                actual = len(parse_claims(body))
                rep = int(o["claims"])
                if abs(actual - rep) > max(2, 0.10 * max(actual, rep)):
                    errors.append(f"{rf.name}: reported {rep} claims in {p} but {actual} parse")
        reads = [str(x) for x in r.get("files_read", [])]
        if role == "answerer":
            bad = [x for x in reads if "/specs/" not in ("/" + x.replace("\\", "/")) and not x.replace("\\", "/").startswith("specs/")
                   and "spec-snapshot" not in x]
            if bad:
                errors.append(f"{rf.name}: answerer read non-spec files (isolation broken): {bad[:5]}")
            if not reads:
                errors.append(f"{rf.name}: answerer did not list files_read")
        if role == "prober":
            bad = [x for x in reads if x.replace("\\", "/").startswith("specs/") or "/specs/modules/" in x]
            if bad:
                errors.append(f"{rf.name}: prober read spec files (blindness broken): {bad[:5]}")
        if role in ("extractor", "reviser") and not reads:
            errors.append(f"{rf.name}: extractor did not list files_read")
    write_json(specs / "_meta" / "verify-report.json", {"checked": checked, "errors": errors})
    for e in errors:
        eprint("ERROR:", e)
    eprint(f"verify: {checked} worker reports, {len(errors)} discrepancies")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
