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

from _common import XREF_RE, eprint, git_head, parse_claims, parse_frontmatter, read_json, resolve_ref, write_json

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--strict-fresh", action="store_true", help="stale commit is an error, not a warning")
    ap.add_argument("--max-fence-lines", type=int, default=20)
    ap.add_argument("--only", action="append", default=[],
                    help="lint only these spec paths (relative to specs dir); unresolved cross-refs become warnings")
    args = ap.parse_args()
    specs = Path(args.specs).resolve()
    repo = Path(args.repo).resolve()
    head = git_head(repo)
    errors: list[str] = []
    warnings: list[str] = []
    all_ids: dict[str, str] = {}
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
            msg = f"{relp}: written at commit {str(commit)[:10]} but HEAD is {head[:10]} (stale; re-run extraction with --update)"
            (errors if args.strict_fresh else warnings).append(msg)
        if fm.get("status") not in ("draft", "provisional", "validated", "weak"):
            errors.append(f"{relp}: status must be draft|provisional|validated|weak (got {fm.get('status')!r})")

        # sections
        headings = {ln.lstrip("#").strip() for ln in body.splitlines() if ln.startswith("#")}
        for sec in REQUIRED_SECTIONS[kind]:
            if sec not in headings:
                errors.append(f"{relp}: missing required section '## {sec}'")

        # claims
        claims = parse_claims(body)
        claims_by_file[relp] = claims
        counts = {"confirmed": 0, "inferred": 0, "gap": 0}
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
                ok, why = resolve_ref(repo, r)
                if not ok:
                    errors.append(f"{relp}:{c['line']}: {cid} ref `{r}`: {why}")
            if len(c["text"]) < 20:
                warnings.append(f"{relp}:{c['line']}: {cid} is very short; one claim = one trigger + one observable outcome")
            if TOOL_MENTION.search(c["text"]):
                errors.append(f"{relp}:{c['line']}: {cid} mentions an AI tool/model; specs must be agent-neutral")
        if kind == "module" and counts["confirmed"] + counts["inferred"] == 0:
            errors.append(f"{relp}: module spec has no confirmed/inferred claims")
        if kind == "module" and not claims:
            errors.append(f"{relp}: no claims parsed; check claim grammar: - [PFX-001] {{confirmed}} `path:L1-L2` text")

        # bullets that look like claims but failed the grammar
        for n, ln in enumerate(body.splitlines(), 1):
            if re.match(r"^\s*[-*]\s+\[[A-Z]", ln) and not any(c["line"] == n for c in claims):
                errors.append(f"{relp}:{n}: bullet starts like a claim but does not parse; expected '- [PFX-001] {{confirmed|inferred|gap}} `ref` text'")

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

    # cross-refs
    for fp in files:
        relp = fp.relative_to(specs).as_posix()
        body = fp.read_text(encoding="utf-8", errors="replace")
        own = {c["id"] for c in claims_by_file.get(relp, [])}
        for xid in set(XREF_RE.findall(body)):
            if xid not in all_ids and xid not in own:
                msg = f"{relp}: cross-reference [{xid}] does not resolve to any claim"
                (warnings if args.only else errors).append(msg + (" (unverifiable with --only)" if args.only else ""))

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
