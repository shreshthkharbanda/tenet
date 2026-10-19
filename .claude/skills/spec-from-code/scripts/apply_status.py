#!/usr/bin/env python3
"""Stamp each module spec's frontmatter `status:` and `fidelity:` from measured results
(validation.json, coverage.json, rebuild/*.json) and regenerate the status table in INDEX.md
between <!-- status:begin --> and <!-- status:end --> markers. Writers never set status; this does.

Usage: apply_status.py <specs_dir>
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _common import eprint, parse_claims, parse_frontmatter, read_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    meta = specs / "_meta"
    val = read_json(meta / "validation.json") if (meta / "validation.json").exists() else {"modules": {}}
    cov = read_json(meta / "coverage.json") if (meta / "coverage.json").exists() else {"modules": {}}
    rows = []
    for fp in sorted((specs / "modules").glob("*.md")):
        text = fp.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        mid = fm.get("module")
        if not mid:
            continue
        claims = parse_claims(body)
        c = {k: sum(1 for x in claims if x["confidence"] == k) for k in ("confirmed", "inferred", "gap")}
        v = val["modules"].get(mid, {})
        cv = cov["modules"].get(mid, {})
        rb = meta / "rebuild" / f"{mid}.json"
        rbs = ""
        if rb.exists():
            r = read_json(rb)
            rbs = f"{r.get('tests_passed', 0)}/{r.get('tests_total', 0)}" if r.get("compiled") else "no compile"
        if v:
            status = v["status"].lower() if v["status"] != "REGRESSION" else "provisional"
            if status == "validated" and (cv.get("file_rate", 1) < 0.95 or cv.get("symbol_rate", 1) < 0.85):
                status = "provisional"
        else:
            status = "draft"
        fid = f"{v['holdout_fidelity']:.0%}" if v else "pending"
        # rewrite frontmatter status / fidelity lines
        head_end = text.find("\n---", 3)
        fm_text = text[3:head_end]
        fm_text = re.sub(r"^status:.*$", f"status: {status}", fm_text, flags=re.M)
        fm_text = re.sub(r"^fidelity:.*(?:\n  .*)*", "", fm_text, flags=re.M).rstrip("\n")
        if v:
            fm_text += f"\nfidelity:\n  holdout: {v['holdout_fidelity']}\n  contradictions: {v['holdout_contradictions']}\n  rounds: {val.get('round', 0)}"
        text = "---" + fm_text.rstrip("\n") + "\n" + text[head_end + 1:]
        fp.write_text(text, encoding="utf-8")
        rows.append(f"| modules/{fp.name} | {c['confirmed']} / {c['inferred']} / {c['gap']} | "
                    f"{cv.get('file_rate', 0):.0%} | {cv.get('symbol_rate', 0):.0%} | {fid} | "
                    f"{v.get('holdout_contradictions', '') if v else ''} | {rbs} | {status} |")
    table = ["| Spec | Claims (confirmed / inferred / gap) | Files cited | Symbols | Held-out fidelity | Held-out contradictions | Rebuild | Status |",
             "|---|---|---:|---:|---:|---:|---|---|", *rows]
    idx = specs / "INDEX.md"
    if idx.exists():
        t = idx.read_text(encoding="utf-8")
        block = "<!-- status:begin -->\n" + "\n".join(table) + "\n<!-- status:end -->"
        if "<!-- status:begin -->" in t:
            t = re.sub(r"<!-- status:begin -->.*?<!-- status:end -->", block, t, flags=re.S)
        else:
            t = t.rstrip("\n") + "\n\n## Status\n" + block + "\n"
        idx.write_text(t, encoding="utf-8")
    eprint(f"status applied to {len(rows)} module specs; INDEX.md table refreshed")
    print("\n".join(table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
