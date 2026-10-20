#!/usr/bin/env python3
"""Gate G3: traceability. Which in-scope files, lines and public symbols does each
module spec actually cite, and do its refs point at the lines its claims talk about?
Writes coverage.json and traceability.md.

Per module, all from the module's OWN spec (cross-cutting refs never count for a module):
  - file rate: owned files (or ranges) cited by some claim
  - symbol rate: public symbols named in the visible spec text (HTML comments and fences do not count)
  - line rate: non-blank owned lines inside a confirmed/inferred claim ref of at most --max-ref-span
    lines. One ref per file satisfied the file rate, so a spec missing the back two-thirds of its
    range passed (red team E1b: 39% of lines); real specs measure 78-91%.
  - unanchored rate: claims none of whose backticked tokens occur in the cited lines +/-5; a ref to
    `::None`, a directory, or lines 1-2 resolves but points at nothing (red team E3); real specs 3-11%.

Usage: check_coverage.py <specs_dir> --repo <root> [--min-file 0.95] [--min-symbol 0.85] [--min-lines 0.6]
                   [--max-unanchored 0.15] [--max-ref-span 120]
Exit 1 if any module is below threshold (list the misses so an extractor can re-run on them).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import (anchor_status, build_ownership, eprint, parse_claims, parse_frontmatter, read_json, ref_path,
                     ref_span, repo_lines, scope_label, visible_text, write_json)

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
    ap.add_argument("--min-lines", type=float, default=0.6,
                    help="share of non-blank owned lines inside some narrow confirmed/inferred claim ref")
    ap.add_argument("--max-unanchored", type=float, default=0.15,
                    help="share of checkable claims whose backticked tokens are absent from the cited lines")
    ap.add_argument("--max-ref-span", type=int, default=120, help="refs wider than this do not count toward line coverage")
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
        spec_text_by_module[fm["module"]] = visible_text(body)
        claims_by_module[fm["module"]] = parse_claims(body)
    # Cross-cutting refs do not count for a module: an extractor that skipped a file a crosscut writer
    # happened to cite passed G3 while traceability.md showed the file with no claims (red team E2).

    def ref_hits(ref: str, item: dict) -> bool:
        if ref_path(ref) != item["path"]:
            return False
        m = re.match(r"^.+?:L?(\d+)(?:-L?(\d+))?$", ref.strip())
        if not m or "::" in ref:
            return True  # bare path or symbol ref: counts for the file
        a = int(m.group(1)); b = int(m.group(2) or a)
        return not (b < item["start"] or a > item["end"])

    def line_cover(item: dict, claims: list) -> tuple[int, int, list[str]]:
        """(non-blank owned lines, covered, uncovered stretches of 20+ non-blank lines)."""
        lines = repo_lines(repo, item["path"])
        nb = [i for i in range(item["start"], min(item["end"], len(lines)) + 1) if lines[i - 1].strip()]
        cov: set[int] = set()
        for c in claims:
            if c["confidence"] == "gap":
                continue
            for r in c["refs"]:
                sp = ref_span(repo, r)
                if sp and sp[0] == item["path"] and sp[2] - sp[1] <= args.max_ref_span:
                    cov.update(range(sp[1], sp[2] + 1))
        holes, run = [], []
        for i in nb:
            if i in cov:
                if len(run) >= 20:
                    holes.append(f"{item['path']}:{run[0]}-{run[-1]}")
                run = []
            else:
                run.append(i)
        if len(run) >= 20:
            holes.append(f"{item['path']}:{run[0]}-{run[-1]}")
        return len(nb), sum(1 for i in nb if i in cov), holes

    report = {"modules": {}, "thresholds": {"file": args.min_file, "symbol": args.min_symbol, "lines": args.min_lines,
                                            "unanchored": args.max_unanchored, "ref_span": args.max_ref_span}}
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
            (covered if ids else uncovered).append(label)
        line_tot = line_cov = 0
        holes: list[str] = []
        for it in items:
            n_, c_, h_ = line_cover(it, claims)
            line_tot, line_cov = line_tot + n_, line_cov + c_
            holes += h_
        checkable, unanchored = 0, []
        for c in claims:
            st = anchor_status(repo, c["refs"], c["text"])
            if st is not None:
                checkable += 1
                if st is False:
                    unanchored.append(c["id"])
        total_syms, hit_syms, missed = 0, 0, []
        for it in items:
            syms = public_symbols(repo / it["path"], lang_by_path.get(it["path"], ""), it["start"], it["end"])
            for s_ in syms:
                total_syms += 1
                # Qualified mentions count: `Class.method`, `module.func`, `Type::method`.
                if re.search(r"(?<![\w])" + re.escape(s_) + r"(?![\w])", body):
                    hit_syms += 1
                else:
                    missed.append(f"{it['path']}::{s_}")
        file_rate = (len(covered) / len(items)) if items else 1.0
        sym_rate = (hit_syms / total_syms) if total_syms else 1.0
        line_rate = (line_cov / line_tot) if line_tot else 1.0
        un_rate = (len(unanchored) / checkable) if checkable else 0.0
        ok = (file_rate >= args.min_file and sym_rate >= args.min_symbol and line_rate >= args.min_lines
              and un_rate <= args.max_unanchored and bool(claims))
        if not ok:
            failing.append(mid)
        report["modules"][mid] = {
            "files": len(items), "files_cited": len(covered), "file_rate": round(file_rate, 3),
            "public_symbols": total_syms, "symbols_mentioned": hit_syms, "symbol_rate": round(sym_rate, 3),
            "lines": line_tot, "lines_covered": line_cov, "line_rate": round(line_rate, 3), "uncovered_stretches": holes[:40],
            "anchor_checkable": checkable, "unanchored": unanchored, "unanchored_rate": round(un_rate, 3),
            "claims": len(claims), "uncovered_files": uncovered, "unmentioned_symbols": missed, "ok": ok,
        }
        md.append(f"## {mid} ({m.get('prefix')})")
        md.append("")
        md.append(f"Files cited: {len(covered)}/{len(items)} ({file_rate:.0%}). Public symbols mentioned: {hit_syms}/{total_syms} ({sym_rate:.0%}). "
                  f"Lines inside a narrow claim ref: {line_cov}/{line_tot} ({line_rate:.0%}). "
                  f"Unanchored claims: {len(unanchored)}/{checkable} ({un_rate:.0%}). Claims: {len(claims)}.")
        md.append("")
        if holes:
            md.append("Owned stretches of 20+ non-blank lines no claim cites: " + ", ".join(f"`{h}`" for h in holes[:20])
                      + (f" (+{len(holes) - 20})" if len(holes) > 20 else ""))
            md.append("")
        if unanchored:
            md.append("Claims whose backticked tokens appear nowhere in the cited lines (check the ref): "
                      + ", ".join(unanchored[:30]) + (f" (+{len(unanchored) - 30})" if len(unanchored) > 30 else ""))
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
        eprint(f"BELOW THRESHOLD: {mid}: files {r['file_rate']:.0%}, symbols {r['symbol_rate']:.0%}, "
               f"lines {r['line_rate']:.0%} (min {args.min_lines:.0%}), unanchored {r['unanchored_rate']:.0%} "
               f"(max {args.max_unanchored:.0%}), claims {r['claims']}")
        for p in r["uncovered_files"][:20]:
            eprint("   uncited file:", p)
        for h in (r["uncovered_stretches"][:10] if r["line_rate"] < args.min_lines else []):
            eprint("   uncited lines:", h)
        if r["unanchored_rate"] > args.max_unanchored:
            eprint("   unanchored claims:", ", ".join(r["unanchored"][:20]))
    eprint(f"coverage: {len(report['modules'])} modules, {len(failing)} below threshold -> _meta/coverage.json, _meta/traceability.md")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
