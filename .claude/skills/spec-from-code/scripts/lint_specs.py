#!/usr/bin/env python3
"""Gate G2: mechanical lint of a specs tree.

Checks: frontmatter present and sane, claim grammar, globally unique claim IDs,
prefix matches the file's declared prefix, confidence values, refs resolve to
real files/lines/symbols, cross-references resolve, required sections present,
commit freshness vs git HEAD, secret patterns, and code-fence leakage.

Usage: lint_specs.py <specs_dir> --repo <repo_root> [--out specs/_meta/lint-report.json] [--strict-fresh]
Exit 1 on any error.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import subprocess

from _common import (XREF_RE, eprint, git_head, parse_claims, parse_frontmatter, read_json, ref_path, ref_span, resolve_ref,
                     write_json)

TABLE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|\d+(?:\.\d+)?")
REQUIRED_SECTIONS = {
    "module": ["Purpose", "Scope and boundaries", "Public surface", "Behaviors", "Validation rules",
               "Error handling", "State and data", "External interactions", "Configuration",
               "Concurrency and ordering", "Implementation notes", "Open questions and gaps", "Test evidence"],
    "overview": ["Purpose", "System map", "Main paths", "Global invariants", "Cross-cutting concerns",
                 "Glossary", "Reading order"],
    "interfaces": ["Entry points", "Error catalog"],
    "data": ["Stores", "Schemas", "Invariants"],
    "config": ["Settings", "Precedence"],
    "operations": ["Build", "Test", "Run"],
}
RESERVED_PREFIX = {"overview": "SYS", "interfaces": "IF", "data": "DATA", "config": "CFG", "operations": "OPS"}
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "private key block"),
    (re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"][A-Za-z0-9+/=_\-]{12,}['\"]"), "credential literal"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{32,}|xox[baprs]-[A-Za-z0-9-]{10,}"), "service token"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}"), "JWT literal"),
]
TOOL_MENTION = re.compile(r"\b(Claude|ChatGPT|GPT-?\d|Copilot|Cursor|Gemini|Codex|subagent|as an AI)\b")
# Stock phrases that state no observable outcome. Each had 0 hits in 2,460 confirmed LiteLLM claims, and
# a hollowed spec of "handles this case appropriately" claims passed lint (red team E1).
UNFALSIFIABLE = re.compile(r"(?i)\b(appropriately|as appropriate|as needed|as expected|properly|correctly|gracefully|"
                           r"handles errors|expected (?:result|behaviou?r)|various|accordingly|and so on|etc)\b")
WIDE_REF = 120  # lines; matches find_overlaps --max-span and coverage --max-ref-span


def changed_since(repo: Path, commit: str, cache: dict):
    if commit in cache:
        return cache[commit]
    try:
        out = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", f"{commit}..HEAD"],
                             capture_output=True, text=True, check=True).stdout.split()
        dirty = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", "HEAD"],
                               capture_output=True, text=True, check=True).stdout.split()
        cache[commit] = set(out) | set(dirty)
    except Exception:
        cache[commit] = None
    return cache[commit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--strict-fresh", action="store_true", help="stale commit is an error, not a warning")
    ap.add_argument("--max-fence-lines", type=int, default=20)
    ap.add_argument("--baseline", default=None,
                    help="a directory of earlier spec files (e.g. _meta/rounds/round-N): any claim ID there that no "
                         "longer exists is an error (IDs are never deleted; default: the latest _meta/rounds/round-*)")
    ap.add_argument("--only", action="append", default=[],
                    help="lint only these spec paths (relative to specs dir); unresolved cross-refs become warnings")
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    repo = Path(args.repo).resolve()
    head = git_head(repo)
    errors: list[str] = []
    warnings: list[str] = []
    all_ids: dict[str, str] = {}
    changed_cache: dict = {}
    per_file: dict[str, dict] = {}
    modules_json = specs / "_meta" / "modules.json"
    mod_prefix = {}
    if modules_json.exists():
        for m in read_json(modules_json).get("modules", []):
            mod_prefix[m.get("id")] = m.get("prefix")

    files = sorted(p for p in specs.rglob("*.md") if "_meta" not in p.relative_to(specs).parts and p.name != "INDEX.md")
    if args.only:
        wanted = {o.strip("/") for o in args.only}
        files = [p for p in files if p.relative_to(specs).as_posix() in wanted]
        missing = wanted - {p.relative_to(specs).as_posix() for p in files}
        for m in missing:
            errors.append(f"--only {m}: file not found under {specs}")
    if not files:
        errors.append(f"no spec files found under {specs}")
    claims_by_file = {}
    cited_rows: list[tuple[str, int, str]] = []
    for fp in files:
        relp = fp.relative_to(specs).as_posix()
        text = fp.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        kind = fm.get("kind")
        if not fm:
            errors.append(f"{relp}: missing frontmatter")
            continue
        if kind not in REQUIRED_SECTIONS:
            errors.append(f"{relp}: frontmatter 'kind' must be one of {sorted(REQUIRED_SECTIONS)} (got {kind!r})")
            continue
        prefix = fm.get("prefix")
        if kind == "module":
            if not fm.get("module"):
                errors.append(f"{relp}: module spec needs 'module: <id>'")
            exp = mod_prefix.get(fm.get("module"))
            if exp and prefix != exp:
                errors.append(f"{relp}: prefix {prefix!r} does not match modules.json prefix {exp!r} for module {fm.get('module')}")
        else:
            exp = RESERVED_PREFIX[kind]
            if prefix != exp:
                errors.append(f"{relp}: {kind} spec must use prefix {exp!r} (got {prefix!r})")
        commit = fm.get("commit")
        if not commit:
            errors.append(f"{relp}: frontmatter missing 'commit'")
        elif head and str(commit) != head:
            # Freshness is per cited file, not per commit: a commit that touches nothing this spec cites
            # (or cites as scope) does not make it stale.
            changed = changed_since(repo, str(commit), changed_cache)
            cited = {ref_path(r) for c in parse_claims(body) for r in c["refs"]}
            scope_globs = fm.get("scope") or []
            if changed is None:
                # An unknown commit makes freshness unverifiable, so it is an error, not one warning among
                # hundreds (red team E22). Staleness of a known commit stays a warning unless --strict-fresh.
                errors.append(f"{relp}: written at commit {str(commit)[:10]}, HEAD is {head[:10]}, and git cannot diff "
                              f"them (unknown or unfetched commit); stamp the commit the spec was written against")
            else:
                from _common import glob_to_regex, parse_scope_entry
                rx = [glob_to_regex(parse_scope_entry(g)[0]) for g in scope_globs if isinstance(g, str)]
                hit = sorted(p for p in changed if p in cited or any(r.match(p) for r in rx))
                if hit:
                    msg = (f"{relp}: stale: {len(hit)} cited or in-scope file(s) changed since {str(commit)[:10]} "
                           f"(e.g. {hit[0]}); re-run extraction with --update")
                    (errors if args.strict_fresh else warnings).append(msg)
        if fm.get("status") not in ("draft", "provisional", "validated", "weak"):
            errors.append(f"{relp}: status must be draft|provisional|validated|weak (got {fm.get('status')!r})")
        elif fm.get("status") != "draft" and (kind != "module" or not re.search(r"(?m)^fidelity:", text.split("\n---", 1)[0])):
            # only apply_status sets a status, from the gates, and it writes the fidelity block with it; a
            # typed `status: validated` reads as measured when nothing measured it (red team B7)
            errors.append(f"{relp}: status {fm.get('status')!r} without the fidelity block apply_status writes; writers "
                          f"leave status: draft (cross-cutting files always stay draft)")

        # sections
        headings = {ln.lstrip("#").strip() for ln in body.splitlines() if ln.startswith("#")}
        for sec in REQUIRED_SECTIONS[kind]:
            if sec not in headings:
                errors.append(f"{relp}: missing required section '## {sec}'")

        # claims
        claims = parse_claims(body)
        claims_by_file[relp] = claims
        counts = {"confirmed": 0, "inferred": 0, "gap": 0}
        seen_text: dict[str, str] = {}
        for c in claims:
            cid = c["id"]
            counts[c["confidence"]] += 1
            if cid in all_ids:
                errors.append(f"{relp}:{c['line']}: duplicate claim id {cid} (also in {all_ids[cid]})")
            all_ids[cid] = f"{relp}:{c['line']}"
            if prefix and not cid.startswith(prefix + "-"):
                errors.append(f"{relp}:{c['line']}: claim {cid} does not use this file's prefix {prefix}")
            if c["confidence"] != "gap" and not c["refs"]:
                errors.append(f"{relp}:{c['line']}: {cid} is {{{c['confidence']}}} but has no source ref")
            if c["confidence"] == "gap" and "?" not in c["text"] and "unknown" not in c["text"].lower() and "cannot" not in c["text"].lower():
                warnings.append(f"{relp}:{c['line']}: {cid} is a gap; phrase it as the open question it leaves")
            for r in c["refs"]:
                if "::" in r and (repo / ref_path(r)).is_file():
                    # a symbol ref must name a definition or assignment (`Class.method` looks inside the class);
                    # a word that merely occurs in the file, like `None`, is not a location (red team E3)
                    ok = ref_span(repo, r) is not None
                    why = f"names no definition or assignment: not found in {ref_path(r)} as one; cite the lines"
                else:
                    ok, why = resolve_ref(repo, r)
                if not ok:
                    errors.append(f"{relp}:{c['line']}: {cid} ref `{r}`: {why}")
                elif c["confidence"] == "confirmed":
                    sp = ref_span(repo, r)
                    if sp and sp[2] - sp[1] > WIDE_REF:
                        warnings.append(f"{relp}:{c['line']}: {cid} ref `{r}` spans {sp[2] - sp[1] + 1} lines; cite the "
                                        f"lines that decide the behavior (wide refs do not count toward line coverage and "
                                        f"pair for reconciliation only through a shared identifier)")
            norm = re.sub(r"\W+", " ", c["text"].lower()).strip()
            if norm in seen_text:
                errors.append(f"{relp}:{c['line']}: {cid} repeats the text of {seen_text[norm]}; one claim per fact")
            seen_text.setdefault(norm, cid)
            if c["confidence"] == "confirmed":
                hit = UNFALSIFIABLE.search(re.sub(r"`[^`\n]*`", " ", c["text"]))  # quoted literals are facts, not prose
                if hit:
                    errors.append(f"{relp}:{c['line']}: {cid} says {hit.group(0)!r}, which no test can falsify; state the "
                                  f"observable outcome (value, message, state change) instead")
            if len(c["text"]) < 20:
                warnings.append(f"{relp}:{c['line']}: {cid} is very short; one claim = one trigger + one observable outcome")
            if TOOL_MENTION.search(c["text"]):
                errors.append(f"{relp}:{c['line']}: {cid} mentions an AI tool/model; specs must be agent-neutral")
            if (re.search(r"`[^`]*<[A-Za-z_][^`>]*>[^`]*`", c["text"])
                    and not re.search(r"(?i)\b(e\.g\.|for example|renders?|rendered|repr|joined|formatted|as in)\b", c["text"])):
                warnings.append(f"{relp}:{c['line']}: {cid} has a message template with <placeholders> but does not say how they "
                                f"render; add one rendered example (precision ladder)")
        if kind == "module" and counts["confirmed"] + counts["inferred"] == 0:
            errors.append(f"{relp}: module spec has no confirmed/inferred claims")
        if kind == "module" and not claims:
            errors.append(f"{relp}: no claims parsed; check claim grammar: - [PFX-001] {{confirmed}} `path:L1-L2` text")

        # bullets that look like claims but failed the grammar
        for n, ln in enumerate(body.splitlines(), 1):
            if re.match(r"^\s*[-*]\s+\[[A-Z]", ln) and not any(c["line"] == n for c in claims):
                errors.append(f"{relp}:{n}: bullet starts like a claim but does not parse; expected '- [PFX-001] {{confirmed|inferred|gap}} `ref` text'")

        # untracked facts in tables: a row that carries values but cites no claim cannot be kept in sync
        sec = ""
        for n, ln in enumerate(body.splitlines(), 1):
            if ln.startswith("## "):
                sec = ln[3:].strip()
            st = ln.strip()
            if st.startswith("|") and sec not in ("Test evidence", "Status", "System map") and XREF_RE.search(st):
                cited_rows.append((relp, n, st))
            if (st.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", st) and sec not in ("Test evidence", "Status", "System map")
                    and not re.search(r"\[?[A-Z][A-Z0-9]{1,11}-\d{3,4}\]?", st)
                    and re.search(r"`[^`]+`|\b\d{2,}\b", st) and not st.lower().startswith(("| entry point", "| id", "| setting", "| module", "| claim", "| condition"))):
                warnings.append(f"{relp}:{n}: table row states values but cites no claim ID; tie it to a claim or it will drift")
        # code fences (language-neutral rule: short exact literals ok, long code dumps not)
        fence_len, in_fence = 0, False
        for n, ln in enumerate(body.splitlines(), 1):
            if ln.strip().startswith("```"):
                if in_fence and fence_len > args.max_fence_lines:
                    warnings.append(f"{relp}:{n}: code fence of {fence_len} lines; specs describe behavior, they do not transcribe code")
                in_fence, fence_len = not in_fence, 0
            elif in_fence:
                fence_len += 1

        # secrets
        for rx, label in SECRET_PATTERNS:
            if rx.search(text):
                errors.append(f"{relp}: possible {label} in spec text; redact and record a gap instead")
        if TOOL_MENTION.search(body) and kind != "operations":
            warnings.append(f"{relp}: mentions an AI tool/model in prose; keep specs agent-neutral")

        per_file[relp] = {"kind": kind, "prefix": prefix, "module": fm.get("module"), "status": fm.get("status"),
                          "claims": counts, "total_claims": len(claims)}

    # cross-refs from the linted files resolve against every spec file, so --only no longer turns a
    # dangling pointer into a warning; pointers into a rewritten file are caught by the full lint (L56)
    known = set(all_ids)
    for fp in sorted(p for p in specs.rglob("*.md") if "_meta" not in p.relative_to(specs).parts):
        if fp not in files:
            known |= {c["id"] for c in parse_claims(fp.read_text(encoding="utf-8", errors="replace"))}
    for fp in files:
        relp = fp.relative_to(specs).as_posix()
        body = fp.read_text(encoding="utf-8", errors="replace")
        for xid in sorted(set(XREF_RE.findall(body))):
            if xid not in known:
                errors.append(f"{relp}: cross-reference [{xid}] does not resolve to any claim")

    # a table row that cites claims states only what they state or their code holds: a name or number in a
    # backticked cell that neither the cited claims nor the files they cite contain is a value that drifted
    # or was made up (red team B6: a row required a setting that exists nowhere, 0 diagnostics). Literals the
    # claims merely word differently are not flagged (that measured 478 rows on LiteLLM; this, 57).
    by_id = {c["id"]: c for cl in claims_by_file.values() for c in cl}
    for fp in sorted(p for p in specs.rglob("*.md") if "_meta" not in p.relative_to(specs).parts and p not in files):
        by_id.update({c["id"]: c for c in parse_claims(fp.read_text(encoding="utf-8", errors="replace"))})
    src_cache: dict[str, str] = {}

    def src(r: str) -> str:
        rp = ref_path(r)
        if rp not in src_cache:
            f = repo / rp
            src_cache[rp] = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
        return src_cache[rp]

    for relp, n, st in cited_rows:
        ids = [x for x in XREF_RE.findall(st) if x in by_id]
        if not ids:
            continue
        cells = re.sub(r"\[?[A-Z][A-Z0-9]{1,11}-\d{3,4}\]?", " ", st)
        said = " ".join(by_id[x]["text"] for x in ids).lower()
        code = "\n".join(src(r) for x in ids for r in by_id[x]["refs"])
        miss = sorted({w for t in re.findall(r"`([^`]+)`", cells) for w in TABLE_TOKEN.findall(re.sub(r"<[^>]*>", " ", t))
                       if w.lower() not in said and w not in code})
        if miss:
            warnings.append(f"{relp}:{n}: table row states {', '.join(miss[:3])}" + (f" (+{len(miss) - 3} more)" if len(miss) > 3 else "")
                            + f", found in neither the claims it cites ({', '.join(ids[:4])}) nor their code; put the value "
                              f"in a claim or fix the row")

    # INDEX.md is a generated map, not a spec: it holds no claims, and its pointers must resolve (red team B7)
    idx = specs / "INDEX.md"
    if idx.exists() and not args.only:
        itext = idx.read_text(encoding="utf-8", errors="replace")
        for c in parse_claims(itext):
            errors.append(f"INDEX.md:{c['line']}: claim {c['id']} in the index; claims belong in a spec file")
        for xid in sorted(set(XREF_RE.findall(itext)) - known):
            errors.append(f"INDEX.md: cross-reference [{xid}] does not resolve to any claim")
        for r in sorted(set(re.findall(r"`([^`\s]+\.\w+(?::\d+(?:-\d+)?)?)`", itext))):
            if ":" in r or "/" in r:
                ok = (specs / r).is_file() or resolve_ref(repo, r)[0]
                if not ok:
                    errors.append(f"INDEX.md: `{r}` names no spec file and resolves to no code")

    # IDs are permanent: one present at the last round's backup must still exist (L69)
    rounds = sorted((specs / "_meta" / "rounds").glob("round-*"), key=lambda d: int(d.name.split("-")[1])
                    if d.name.split("-")[1].isdigit() else -1) if (specs / "_meta" / "rounds").exists() else []
    base = Path(args.baseline).resolve() if args.baseline else (rounds[-1] if rounds else None)
    if base and base.exists():
        linted = {fp.name for fp in files}
        for bf in sorted(base.glob("*.md")):
            if args.only and bf.name not in linted:
                continue
            gone = {c["id"] for c in parse_claims(bf.read_text(encoding="utf-8", errors="replace"))} - known
            for cid in sorted(gone):
                errors.append(f"{bf.name}: claim {cid} existed at {base.name} and was deleted; rewrite it in place instead")
    report = {"errors": errors, "warnings": warnings, "files": per_file, "total_claims": len(all_ids), "head": head}
    if args.out:
        write_json(Path(args.out), report)
    for w in warnings[:200]:
        eprint("WARN:", w)
    for e in errors[:400]:
        eprint("ERROR:", e)
    eprint(f"lint: {len(files)} spec files, {len(all_ids)} claims, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
