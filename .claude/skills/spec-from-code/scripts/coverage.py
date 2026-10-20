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

from _common import build_ownership, eprint, parse_claims, parse_frontmatter, read_json, ref_path, scope_label, write_json

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


CLASSY = re.compile(r"^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+|internal\s+|abstract\s+|final\s+|sealed\s+|"
                    r"static\s+|data\s+|open\s+|partial\s+)*(?:class|interface|object|trait|struct|enum|record|module|impl|defmodule)\b")
OPENER = re.compile(r"^\s*(?:@|(?:async\s+)?def\s|class\s|func\s|fn\s|function\s|fun\s|defmodule\s|def\s|"
                    r"(?:export\s+)?(?:public|private|protected|internal|static|abstract|final|sealed|override|suspend|async)\s)")


def public_symbols(fp: Path, lang: str, start: int = 1, end: int = 10**9) -> list[str]:
    """Names a caller can reach: top-level definitions and members of classes nested only in classes.
    A definition inside a function body (closures, local wrapper classes) is not public surface, so it is
    skipped; nesting is read from indentation, which tracks it in every mainstream language's style."""
    rxs = SYMBOL_RES.get(lang)
    if not rxs:
        return []
    out = []
    stack: list[tuple[int, str]] = []  # (indent, "class" | "func")
    try:
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for i, ln in enumerate(lines, 1):
        if not ln.strip() or ln.lstrip().startswith(("#", "//", "*", "/*", "@")):
            continue
        ind = len(ln) - len(ln.lstrip())
        if ln.lstrip().startswith((")", "]")):
            continue  # end of a multi-line signature or literal, not the end of a block ("}" still is)
        while stack and stack[-1][0] >= ind:
            stack.pop()
        is_open = bool(OPENER.match(ln)) or bool(CLASSY.match(ln))
        kind = "class" if CLASSY.match(ln) else "func"
        reachable = all(k == "class" for _, k in stack)
        if is_open and start <= i <= end and reachable:
            for rx in rxs:
                m = rx.match(ln)
                if m:
                    name = m.group(1)
                    if not PRIVATE_HINT.match(name) and name not in ("if", "for", "while", "switch", "return", "new", "else", "catch"):
                        out.append(name)
                    break
        if is_open:
            stack.append((ind, kind))
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
    own = build_ownership(mods, inv["files"], repo)
    lang_by_path = {f["path"]: f["lang"] for f in inv["files"]}

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
    xc_refs: list[str] = []
    for name in ("00-overview.md", "01-interfaces.md", "02-data.md", "03-config.md", "04-operations.md"):
        p = specs / name
        if p.exists():
            _, body = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
            for c in parse_claims(body):
                xc_refs += c["refs"]

    def ref_hits(ref: str, item: dict) -> bool:
        if ref_path(ref) != item["path"]:
            return False
        m = re.match(r"^.+?:(\d+)(?:-(\d+))?$", ref.strip())
        if not m or "::" in ref:
            return True  # bare path or symbol ref: counts for the file
        a = int(m.group(1)); b = int(m.group(2) or a)
        return not (b < item["start"] or a > item["end"])

    report = {"modules": {}, "thresholds": {"file": args.min_file, "symbol": args.min_symbol}}
    md = ["# Traceability: source -> claims", "",
          "Generated by coverage.py. A file (or line range) with no claims is trivial, dead, or a spec gap; the extractor must say which.", ""]
    failing = []
    for m in mods.get("modules", []):
        mid = m["id"]
        items = own["assign"].get(mid, [])
        claims = claims_by_module.get(mid, [])
        body = spec_text_by_module.get(mid, "")
        refs_by_item: dict[str, list[str]] = {}
        covered, uncovered = [], []
        for it in items:
            label = scope_label(it)
            ids = sorted({c["id"] for c in claims for r in c["refs"] if ref_hits(r, it)})
            refs_by_item[label] = ids
            if ids or any(ref_hits(r, it) for r in xc_refs):
                covered.append(label)
            else:
                uncovered.append(label)
        total_syms, hit_syms, missed = 0, 0, []
        for it in items:
            syms = public_symbols(repo / it["path"], lang_by_path.get(it["path"], ""), it["start"], it["end"])
            for s_ in syms:
                total_syms += 1
                if re.search(r"(?<![\w.])" + re.escape(s_) + r"(?![\w])", body):
                    hit_syms += 1
                else:
                    missed.append(f"{it['path']}::{s_}")
        file_rate = (len(covered) / len(items)) if items else 1.0
        sym_rate = (hit_syms / total_syms) if total_syms else 1.0
        ok = file_rate >= args.min_file and sym_rate >= args.min_symbol and bool(claims)
        if not ok:
            failing.append(mid)
        report["modules"][mid] = {
            "files": len(items), "files_cited": len(covered), "file_rate": round(file_rate, 3),
            "public_symbols": total_syms, "symbols_mentioned": hit_syms, "symbol_rate": round(sym_rate, 3),
            "claims": len(claims), "uncovered_files": uncovered, "unmentioned_symbols": missed, "ok": ok,
        }
        md.append(f"## {mid} ({m.get('prefix')})")
        md.append("")
        md.append(f"Files cited: {len(covered)}/{len(items)} ({file_rate:.0%}). Public symbols mentioned: {hit_syms}/{total_syms} ({sym_rate:.0%}). Claims: {len(claims)}.")
        md.append("")
        md.append("| File | LOC | Claims |")
        md.append("|---|---:|---|")
        for it in items:
            ids = refs_by_item.get(scope_label(it), [])
            shown = ", ".join(ids[:12]) + (f" (+{len(ids) - 12})" if len(ids) > 12 else "")
            md.append(f"| `{scope_label(it)}` | {it['loc']} | {shown or '**none**'} |")
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
