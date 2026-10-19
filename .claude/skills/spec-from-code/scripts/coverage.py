#!/usr/bin/env python3
"""Gate G3: traceability. Which in-scope files and public symbols does each
module spec actually cite? Writes coverage.json and traceability.md.

Usage: coverage.py <specs_dir> --repo <root> [--min-file 0.95] [--min-symbol 0.85]
Exit 1 if any module is below threshold (list the misses so an extractor can re-run on them).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import eprint, glob_to_regex, parse_claims, parse_frontmatter, read_json, ref_path, write_json

SYMBOL_RES = {
    "python": [re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z]\w*)\s*\("), re.compile(r"^\s*class\s+([A-Za-z]\w*)")],
    "javascript": [re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$]\w*)"),
                   re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$]\w*)"),
                   re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_$]\w*)")],
    "java": [re.compile(r"^\s*(?:public|protected)\s+(?:static\s+|final\s+|abstract\s+|synchronized\s+|default\s+)*[\w<>\[\]?,.\s]+?\s+([a-z]\w*)\s*\("),
             re.compile(r"^\s*(?:public\s+|protected\s+)?(?:final\s+|abstract\s+|static\s+|sealed\s+)*(?:class|interface|enum|record)\s+([A-Z]\w*)")],
    "go": [re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)\s*\("), re.compile(r"^type\s+([A-Z]\w*)\s")],
    "rust": [re.compile(r"^\s*pub(?:\([^)]*\))?\s+(?:async\s+)?fn\s+(\w+)"), re.compile(r"^\s*pub(?:\([^)]*\))?\s+(?:struct|enum|trait|type)\s+(\w+)")],
    "ruby": [re.compile(r"^\s*def\s+(?:self\.)?([a-z_]\w*[?!]?)"), re.compile(r"^\s*(?:class|module)\s+([A-Z]\w*)")],
    "csharp": [re.compile(r"^\s*public\s+(?:static\s+|async\s+|virtual\s+|override\s+)*[\w<>\[\]?,.\s]+?\s+([A-Z]\w*)\s*\("),
               re.compile(r"^\s*public\s+(?:static\s+|abstract\s+|sealed\s+|partial\s+)*(?:class|interface|enum|record|struct)\s+([A-Z]\w*)")],
    "php": [re.compile(r"^\s*(?:public\s+)?(?:static\s+)?function\s+([A-Za-z_]\w*)"), re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+([A-Za-z_]\w*)")],
    "scala": [re.compile(r"^\s*def\s+([A-Za-z_]\w*)"), re.compile(r"^\s*(?:case\s+)?(?:class|object|trait)\s+([A-Za-z_]\w*)")],
    "kotlin": [re.compile(r"^\s*(?:public\s+|internal\s+)?(?:suspend\s+)?fun\s+(?:<[^>]+>\s*)?(?:[\w.]+\.)?([A-Za-z_]\w*)"),
               re.compile(r"^\s*(?:public\s+|internal\s+)?(?:data\s+|sealed\s+|abstract\s+|open\s+|enum\s+)*(?:class|interface|object)\s+([A-Za-z_]\w*)")],
    "elixir": [re.compile(r"^\s*def\s+([a-z_]\w*[?!]?)"), re.compile(r"^\s*defmodule\s+([\w.]+)")],
    "swift": [re.compile(r"^\s*(?:public\s+|open\s+)(?:static\s+)?func\s+([A-Za-z_]\w*)"), re.compile(r"^\s*(?:public\s+|open\s+)(?:final\s+)?(?:class|struct|enum|protocol)\s+([A-Za-z_]\w*)")],
}
SYMBOL_RES["typescript"] = SYMBOL_RES["javascript"]
PRIVATE_HINT = re.compile(r"^_")


def public_symbols(fp: Path, lang: str) -> list[str]:
    rxs = SYMBOL_RES.get(lang)
    if not rxs:
        return []
    out = []
    try:
        for ln in fp.read_text(encoding="utf-8", errors="replace").splitlines():
            for rx in rxs:
                m = rx.match(ln)
                if m:
                    name = m.group(1)
                    if lang == "python" and PRIVATE_HINT.match(name):
                        continue
                    if name in ("if", "for", "while", "switch", "return", "new", "else", "catch"):
                        continue
                    out.append(name)
                    break
    except OSError:
        pass
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--min-file", type=float, default=0.95)
    ap.add_argument("--min-symbol", type=float, default=0.85)
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    repo = Path(args.repo).resolve()
    inv = read_json(specs / "_meta" / "inventory.json")
    mods = read_json(specs / "_meta" / "modules.json")
    files_by_path = {f["path"]: f for f in inv["files"]}
    in_scope = [f for f in inv["files"] if f["kind"] == "source" and not f["is_test"] and not f["is_generated"]]
    ex_rx = [glob_to_regex(e["glob"]) for e in mods.get("excluded", []) if e.get("glob")]

    # gather claims per module from module specs
    spec_text_by_module: dict[str, str] = {}
    claims_by_module: dict[str, list] = {}
    for fp in sorted((specs / "modules").glob("*.md")) if (specs / "modules").exists() else []:
        text = fp.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        if fm.get("kind") != "module" or not fm.get("module"):
            continue
        spec_text_by_module[fm["module"]] = body
        claims_by_module[fm["module"]] = parse_claims(body)
    # cross-cutting specs also cite files; count those refs toward file coverage
    xc_refs: set[str] = set()
    for name in ("00-overview.md", "01-interfaces.md", "02-data.md", "03-config.md", "04-operations.md"):
        p = specs / name
        if p.exists():
            _, body = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
            for c in parse_claims(body):
                for r in c["refs"]:
                    xc_refs.add(ref_path(r))

    report = {"modules": {}, "thresholds": {"file": args.min_file, "symbol": args.min_symbol}}
    md = ["# Traceability: source -> claims", "",
          "Generated by coverage.py. A file with no claims is either trivial, dead, or a spec gap; the extractor must say which.", ""]
    failing = []
    for m in mods.get("modules", []):
        mid = m["id"]
        rxs = [glob_to_regex(g) for g in m.get("globs", [])]
        mfiles = [f for f in in_scope if any(rx.match(f["path"]) for rx in rxs) and not any(rx.match(f["path"]) for rx in ex_rx)]
        claims = claims_by_module.get(mid, [])
        body = spec_text_by_module.get(mid, "")
        refs_by_file: dict[str, list[str]] = {}
        for c in claims:
            for r in c["refs"]:
                refs_by_file.setdefault(ref_path(r), []).append(c["id"])
        covered_files = [f["path"] for f in mfiles if f["path"] in refs_by_file or f["path"] in xc_refs]
        uncovered_files = [f["path"] for f in mfiles if f["path"] not in refs_by_file and f["path"] not in xc_refs]
        # symbols
        total_syms, hit_syms, missed = 0, 0, []
        for f in mfiles:
            syms = public_symbols(repo / f["path"], f["lang"])
            for s in syms:
                total_syms += 1
                if re.search(r"(?<![\w.])" + re.escape(s) + r"(?![\w])", body):
                    hit_syms += 1
                else:
                    missed.append(f"{f['path']}::{s}")
        file_rate = (len(covered_files) / len(mfiles)) if mfiles else 1.0
        sym_rate = (hit_syms / total_syms) if total_syms else 1.0
        ok = file_rate >= args.min_file and sym_rate >= args.min_symbol and bool(claims)
        if not ok:
            failing.append(mid)
        report["modules"][mid] = {
            "files": len(mfiles), "files_cited": len(covered_files), "file_rate": round(file_rate, 3),
            "public_symbols": total_syms, "symbols_mentioned": hit_syms, "symbol_rate": round(sym_rate, 3),
            "claims": len(claims), "uncovered_files": uncovered_files, "unmentioned_symbols": missed, "ok": ok,
        }
        md.append(f"## {mid} ({m.get('prefix')})")
        md.append("")
        md.append(f"Files cited: {len(covered_files)}/{len(mfiles)} ({file_rate:.0%}). Public symbols mentioned: {hit_syms}/{total_syms} ({sym_rate:.0%}). Claims: {len(claims)}.")
        md.append("")
        md.append("| File | LOC | Claims |")
        md.append("|---|---:|---|")
        for f in mfiles:
            ids = sorted(set(refs_by_file.get(f["path"], [])))
            shown = ", ".join(ids[:12]) + (f" (+{len(ids) - 12})" if len(ids) > 12 else "")
            md.append(f"| `{f['path']}` | {f['loc']} | {shown or '**none**'} |")
        if missed:
            md.append("")
            md.append("Public symbols not mentioned anywhere in the module spec:")
            for s in missed[:60]:
                md.append(f"- `{s}`")
            if len(missed) > 60:
                md.append(f"- ... and {len(missed) - 60} more")
        md.append("")
    write_json(specs / "_meta" / "coverage.json", report)
    (specs / "_meta" / "traceability.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for mid in failing:
        r = report["modules"][mid]
        eprint(f"BELOW THRESHOLD: {mid}: files {r['file_rate']:.0%}, symbols {r['symbol_rate']:.0%}, claims {r['claims']}")
        for p in r["uncovered_files"][:20]:
            eprint("   uncited file:", p)
    eprint(f"coverage: {len(report['modules'])} modules, {len(failing)} below threshold -> _meta/coverage.json, _meta/traceability.md")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
