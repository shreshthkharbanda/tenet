"""Shared helpers for spec-from-code scripts. Stdlib only, deterministic."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Claim grammar:
#   - [PREFIX-NNN] {confidence} `path:L1-L2`, `path::Symbol` Claim text.
# Confidence is one of confirmed | inferred | gap. Refs are optional only for
# {gap} claims (a gap may point at nothing yet), required otherwise.
CLAIM_RE = re.compile(
    r"^\s*[-*]\s+\[(?P<id>[A-Z][A-Z0-9]{1,11}-\d{3,4})\]\s+"
    r"\{(?P<conf>confirmed|inferred|gap)\}\s*"
    r"(?P<rest>\S.*)$"
)
# A backticked span is a ref only if it is shaped like a location: it has a slash or a file
# extension, optionally followed by :L1[-L2] or ::Symbol. Otherwise it is the start of the claim
# text (e.g. "`add` returns ..."), which must not be swallowed as a ref.
REF_SHAPE = re.compile(
    r"^(?:(?:[\w.@+-]+/)*[\w@+-][\w.@+-]*\.[A-Za-z0-9]{1,8}(?::L?\d+(?:-L?\d+)?|::[\w.$<>-]+)?"  # file, opt. lines/symbol
    r"|(?:[\w.@+-]+/){2,})$"                                                                  # dir: 2+ segments
)


def split_refs(rest: str) -> tuple[list[str], str]:
    refs: list[str] = []
    i = 0
    while True:
        m = re.match(r"\s*`([^`\n]+)`\s*,?\s*", rest[i:])
        if not m or not REF_SHAPE.match(m.group(1).strip()):
            break
        refs.append(m.group(1).strip())
        i += m.end()
    return refs, rest[i:].strip()
REF_RE = re.compile(r"`([^`\n]+)`")
XREF_RE = re.compile(r"\[([A-Z][A-Z0-9]{1,11}-\d{3,4})\]")
ID_RE = re.compile(r"^([A-Z][A-Z0-9]{1,11})-(\d{3,4})$")

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "third_party", "thirdparty", "dist", "build",
    "target", "out", ".venv", "venv", "env", "__pycache__", ".idea", ".vscode",
    "coverage", ".next", ".nuxt", ".cache", ".tox", ".mypy_cache", ".pytest_cache",
    "site-packages", "Pods", "DerivedData", ".gradle", ".terraform", "bower_components",
    ".eggs", "htmlcov", ".ruff_cache", ".parcel-cache", ".turbo",
}


def eprint(*a: object) -> None:
    print(*a, file=sys.stderr)


def read_json(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_json(p: Path, obj: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


EVAL_ROLES = {"prober", "answerer", "judge", "control", "judge-auditor", "story-reader", "story-scorer"}


def eval_dir(specs: Path) -> Path:
    """Where everything that defines or reveals the fidelity score lives: probes with reference answers,
    answers, judgments, validation reports, probe corrections, the judge-audit sample, and the reports of
    the roles that touch them. It sits OUTSIDE the specs dir and the repo, so a writer's recursive grep
    over either never reaches a held-out answer (L57). Set at Phase 0 by inventory.py (--eval) in
    _meta/run.json; the default is a sibling `<specs>-eval`."""
    specs = Path(specs).resolve()
    run = specs / "_meta" / "run.json"
    if run.exists():
        d = read_json(run).get("eval_dir")
        if d:
            return Path(d)
    return specs.parent / (specs.name + "-eval")


def reports_dirs(specs: Path) -> list[Path]:
    """Worker-report directories: writers report under the specs dir, eval roles under the eval dir."""
    return [Path(specs).resolve() / "_meta" / "worker-reports", eval_dir(specs) / "worker-reports"]


ALL_SCOPE_ROLES = {"surveyor", "reconciler", "redteam", "reader", "lifecycle-checker", "judge-auditor", "control",
                   "interfaces", "data", "config", "operations"}


def expected_report(brief: Path) -> str:
    """The worker-report stem a rendered brief implies (dispatch.py unfinished and verify_reports.py both
    use this): <role>-<module>[-round-N], with module "all" for whole-spec roles."""
    brief = Path(brief)
    n = brief.stem
    if n == "_brief":
        parts = brief.parent.name.split("-", 1)
        return f"rebuilder-{parts[1]}" if len(parts) == 2 and parts[0] == "rebuild" else "control-all"
    n = n[len("audit-"):] if n.startswith("audit-") else n
    m = re.match(r"^(.+?)-round-(\d+)$", n)
    base, rnd = (m.group(1), m.group(2)) if m else (n, None)
    if base in ALL_SCOPE_ROLES:
        return f"{base}-all" + (f"-round-{rnd}" if rnd else "")
    return n


def read_jsonl(p: Path) -> list[dict]:
    rows = []
    with open(p, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{p}:{n}: invalid JSON: {e}")
    return rows


def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def git_head(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a gitignore-ish glob (supports **, *, ?) to a regex over
    forward-slash relative paths. '**' matches across directories."""
    pattern = pattern.replace("\\", "/").lstrip("./")
    i, out = 0, ""
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i:i + 3] == "**/":
                out += "(?:.*/)?"
                i += 3
                continue
            if pattern[i:i + 2] == "**":
                out += ".*"
                i += 2
                continue
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c in ".+^$(){}[]|":
            out += "\\" + c
        else:
            out += c
        i += 1
    # A bare directory pattern like "src/auth" should match everything under it.
    return re.compile(f"^(?:{out})(?:/.*)?$")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML-ish frontmatter parser: top-level `key: value` and
    `key:` followed by `  - item` lists. Enough for spec headers."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block = text[3:end].strip("\n")
    body = text[end + 4:]
    data: dict = {}
    key = None
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key, val = m.group(1), m.group(2).strip()
            if val == "":
                data[key] = []
            else:
                data[key] = _scalar(val)
        elif key is not None and re.match(r"^\s+-\s+", line):
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(_scalar(re.sub(r"^\s+-\s+", "", line).strip()))
        elif key is not None and re.match(r"^\s+\w[\w-]*:\s*", line):
            # nested map (e.g. fidelity:), keep as dict of scalars
            if not isinstance(data.get(key), dict):
                data[key] = {}
            k2, v2 = line.strip().split(":", 1)
            data[key][k2.strip()] = _scalar(v2.strip())
    return data, body


def _scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        if re.match(r"^-?\d+$", v):
            return int(v)
        if re.match(r"^-?\d+\.\d+$", v):
            return float(v)
    except ValueError:
        pass
    return v


def parse_claims(text: str) -> list[dict]:
    """Return claims found in a spec body with line numbers and section."""
    claims = []
    section, subsection = "", ""
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            if level <= 2:
                section, subsection = title, ""
            else:
                subsection = title
            continue
        m = CLAIM_RE.match(line)
        if not m:
            continue
        refs, text = split_refs(m.group("rest"))
        if not text:
            continue
        claims.append({
            "id": m.group("id"),
            "confidence": m.group("conf"),
            "refs": refs,
            "text": text,
            "line": n,
            "section": section,
            "subsection": subsection,
        })
    return claims


def file_line_count(p: Path) -> int:
    with open(p, "rb") as f:
        return sum(1 for _ in f)


def resolve_ref(repo: Path, ref: str) -> tuple[bool, str]:
    """Validate `path:L1-L2`, `path:L1`, `path::Symbol`, or bare `path`."""
    ref = ref.strip()
    if "::" in ref:
        path, sym = ref.split("::", 1)
        fp = repo / path
        if not fp.is_file():
            return False, f"file not found: {path}"
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return False, f"unreadable: {path}: {e}"
        if not re.search(r"\b" + re.escape(sym.strip()) + r"\b", content):
            return False, f"symbol '{sym}' not found in {path}"
        return True, ""
    m = re.match(r"^(.+?):L?(\d+)(?:-L?(\d+))?$", ref)
    if m:
        path, a, b = m.group(1), int(m.group(2)), m.group(3)
        fp = repo / path
        if not fp.is_file():
            return False, f"file not found: {path}"
        n = file_line_count(fp)
        b_int = int(b) if b else a
        if a < 1 or b_int < a:
            return False, f"bad line range in {ref}"
        if b_int > n:
            return False, f"line {b_int} beyond end of {path} ({n} lines)"
        return True, ""
    fp = repo / ref
    if fp.exists():
        return True, ""
    return False, f"path not found: {ref}"


def ref_path(ref: str) -> str:
    ref = ref.strip()
    if "::" in ref:
        return ref.split("::", 1)[0]
    m = re.match(r"^(.+?):L?(\d+)(?:-L?(\d+))?$", ref)
    return m.group(1) if m else ref


def rel(p: Path, root: Path) -> str:
    return os.path.relpath(p, root).replace(os.sep, "/")


# ---------------------------------------------------------------------------
# Scope entries and module ownership (shared by check_shards, coverage,
# changed_modules, render_briefs). A module "glob" entry is either a glob
# ("src/auth/**") or a line range of one exact file ("litellm/router.py:1-1450").
# Ranges exist because some files are larger than one extractor can hold
# (LiteLLM's router.py is 14.6k lines); split_file.py proposes the cut points.
RANGE_ENTRY_RE = re.compile(r"^(?P<path>[^*?\[]+?):(?P<a>\d+)-(?P<b>\d+)$")


def parse_scope_entry(entry: str):
    m = RANGE_ENTRY_RE.match(entry.strip())
    if m:
        return m.group("path"), int(m.group("a")), int(m.group("b"))
    return entry.strip(), None, None


def in_scope(rec: dict) -> bool:
    return (rec.get("kind") == "source" and not rec.get("is_test") and not rec.get("is_generated")
            and rec.get("in_scope", True))


def count_nonblank(repo: Path, path: str, a: int, b: int) -> int:
    try:
        lines = (repo / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    return sum(1 for ln in lines[a - 1:b] if ln.strip())


def build_ownership(mods_json: dict, files: list[dict], repo: Path) -> dict:
    """Assign every in-scope inventory record to modules.

    Returns {"assign": {mid: [{"path", "start", "end", "loc"}]}, "excluded": [paths],
             "unassigned": [paths], "multi": [{"path", "modules"}],
             "range_errors": [str]}
    A whole-file assignment has start=1, end=<lines>.
    """
    modules = mods_json.get("modules", [])
    ex_rx = [glob_to_regex(e["glob"]) for e in mods_json.get("excluded", []) if e.get("glob")]
    whole: list[tuple[str, list]] = []
    ranges: dict[str, list[tuple[str, int, int]]] = {}
    for m in modules:
        rxs = []
        for g in m.get("globs", []):
            path, a, b = parse_scope_entry(g)
            if a is None:
                rxs.append(glob_to_regex(path))
            else:
                ranges.setdefault(path, []).append((m["id"], a, b))
        whole.append((m["id"], rxs))
    out = {"assign": {m["id"]: [] for m in modules if "id" in m}, "excluded": [], "unassigned": [],
           "multi": [], "range_errors": []}
    seen_range_paths = set()
    for f in files:
        if not in_scope(f):
            continue
        p = f["path"]
        if any(rx.match(p) for rx in ex_rx):
            out["excluded"].append(p)
            continue
        n = f.get("lines") or f.get("loc", 0)
        owners = [mid for mid, rxs in whole if any(rx.match(p) for rx in rxs)]
        rs = sorted(ranges.get(p, []), key=lambda t: t[1])
        if rs:
            seen_range_paths.add(p)
        if owners and rs:
            out["multi"].append({"path": p, "modules": owners + [r[0] for r in rs]})
            continue
        if len(owners) > 1:
            out["multi"].append({"path": p, "modules": owners})
            continue
        if len(owners) == 1:
            out["assign"][owners[0]].append({"path": p, "start": 1, "end": n, "loc": f.get("loc", 0), "whole": True})
            continue
        if not rs:
            out["unassigned"].append(p)
            continue
        expect = 1
        for mid, a, b in rs:
            if a > expect:
                out["range_errors"].append(f"{p}: lines {expect}-{a - 1} not assigned to any module")
            elif a < expect:
                out["range_errors"].append(f"{p}: range {a}-{b} ({mid}) overlaps the previous range ending at {expect - 1}")
            if b > n:
                out["range_errors"].append(f"{p}: range {a}-{b} ({mid}) ends past end of file ({n} lines); re-run split_file.py")
            expect = max(expect, b + 1)
            out["assign"].setdefault(mid, []).append({"path": p, "start": a, "end": min(b, n), "whole": False,
                                                       "loc": count_nonblank(repo, p, a, min(b, n))})
        if expect <= n:
            out["range_errors"].append(f"{p}: lines {expect}-{n} not assigned to any module")
    for p in ranges:
        if p not in seen_range_paths:
            out["range_errors"].append(f"range entries name {p}, which is not an in-scope source file")
    return out


def scope_label(item: dict) -> str:
    """'path' for whole files, 'path:a-b' for ranges."""
    if item.get("whole"):
        return item["path"]
    return f"{item['path']}:{item['start']}-{item['end']}"


# Universal claims (always / never / unless / only / "takes effect" / "is ignored" ...) assert something
# about every path. In the LiteLLM audit they failed falsification at 29% against 8% for other claims:
# writers check the paths they read and generalize. They get priority in falsification sampling.
UNIVERSAL_RE = re.compile(
    r"(?i)\b(always|never|every|any|only|unless|regardless|none|all\s+(?:paths|callers|calls|cases)|"
    r"no\s+\w+\s+(?:is|are|ever)|is\s+(?:not\s+)?(?:retried|validated|checked|ignored)|not\s+(?:retried|validated|checked|"
    r"called|read|written)|does not|cannot|takes effect)\b")


def is_universal(text: str) -> bool:
    return bool(UNIVERSAL_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Ref geometry: which lines a ref actually points at. Shared by coverage (line rate, anchor check),
# lint (symbol refs must name a definition), check_ownership (owners of symbol refs into split
# files) and find_overlaps. The round-1 red team showed that "the ref resolves" says nothing about
# whether it points at the behavior: `::None`, a directory, or lines 1-2 all resolved (L57).
LINE_REF_RE = re.compile(r"^(.+?):L?(\d+)(?:-L?(\d+))?$")
DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc")
_LINES_CACHE: dict[str, list[str]] = {}

_DEF_MODS = (r"(?:(?:export|default|pub(?:\([^)]*\))?|public|private|protected|internal|static|final|abstract|sealed|"
             r"async|override|virtual|synchronized|open|data|suspend|inline|unsafe|extern)\s+)*")
_DEF_KW = (r"(?:def|class|function|func|fn|fun|interface|struct|enum|trait|type|module|object|record|const|let|var|"
           r"val|defmodule|defp|macro|impl)")
_METHOD_MODS = (r"(?:(?:public|private|protected|internal|static|final|abstract|synchronized|override|virtual|async|"
                r"sealed|default)\s+)+")


def repo_lines(repo: Path, path: str) -> list[str]:
    key = str(repo / path)
    if key not in _LINES_CACHE:
        try:
            _LINES_CACHE[key] = (repo / path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            _LINES_CACHE[key] = []
    return _LINES_CACHE[key]


def _def_line(lines: list[str], name: str, lo: int = 0, hi: int | None = None) -> int | None:
    """0-based line of the definition (or assignment) of `name` within lines[lo:hi], by priority:
    a definition keyword, a Go method, a modifier-led method declaration, an assignment, a field."""
    hi = len(lines) if hi is None else hi
    if name in ("None", "True", "False", "null", "nil", "undefined", "self", "this"):
        return None
    n = re.escape(name)
    typ = r"[\w.]+(?:\[[^\]\n]*\]|<[^>\n]*>)?"
    rxs = [re.compile(r"^\s*" + _DEF_MODS + _DEF_KW + r"\s+\*?\s*" + n + r"(?![\w$])"),
           re.compile(r"^func\s+\([^)]*\)\s*" + n + r"\s*[(\[]"),
           re.compile(r"^\s*" + _METHOD_MODS + r"[\w<>\[\],.?]+(?:\s+[\w<>\[\],.?]+)*\s+" + n + r"\s*\("),
           re.compile(r"^\s*(?:self\.|this\.|@)?" + n + r"\s*(?::[^=\n]+)?=(?!=)"),
           # a quoted mapping key, or a field declared with a bare type (`name: int`, `name?: string;`)
           re.compile(r"^\s*['\"]" + n + r"['\"]\s*:"),
           re.compile(r"^\s*" + n + r"\??\s*:\s*" + typ + r"(?:\s*\|\s*" + typ + r")*\s*[;,]?\s*(?:#.*|//.*)?$")]
    for rx in rxs:
        for i in range(lo, min(hi, len(lines))):
            if rx.match(lines[i]):
                return i
    return None


def _block_end(lines: list[str], i: int) -> int:
    """Last 0-based line of the block opened at line i, read from indentation: deeper lines belong to it,
    and a closer (`)`, `]`, `}`) at the opener's indent ends it."""
    ind = len(lines[i]) - len(lines[i].lstrip())
    end, k = i, i + 1
    while k < len(lines):
        s = lines[k]
        if not s.strip():
            k += 1
            continue
        ki = len(s) - len(s.lstrip())
        if ki > ind or (ki == ind and s.lstrip()[:1] in ")]}"):
            end = k
            k += 1
            continue
        break
    return end


def symbol_span(repo: Path, path: str, sym: str) -> tuple[int, int] | None:
    """1-based (start, end) of the definition `sym` names in path (`Class.method` is looked up inside
    the class first), or None when it names no definition or assignment."""
    lines = repo_lines(repo, path)
    parts = [p for p in re.split(r"\.|::", sym.strip()) if p]
    if not lines or not parts:
        return None
    lo, hi, found = 0, len(lines), None
    for p in parts:
        i = _def_line(lines, p, lo, hi)
        if i is None:
            found = None
            break
        found = (i, _block_end(lines, i))
        lo, hi = found[0], found[1] + 1
    if found is None and len(parts) > 1:
        i = _def_line(lines, parts[-1])
        found = (i, _block_end(lines, i)) if i is not None else None
    return (found[0] + 1, found[1] + 1) if found else None


def ref_span(repo: Path, ref: str) -> tuple[str, int, int] | None:
    """(path, start, end) a line or symbol ref points at; None for a bare path, a directory, or a
    symbol that names no definition."""
    ref = ref.strip()
    if "::" in ref:
        path, sym = ref.split("::", 1)
        sp = symbol_span(repo, path, sym)
        return (path, sp[0], sp[1]) if sp else None
    m = LINE_REF_RE.match(ref)
    if m:
        a = int(m.group(2))
        return m.group(1), a, int(m.group(3) or a)
    return None


def visible_text(body: str) -> str:
    """Spec text a reader sees: HTML comments and fenced blocks removed."""
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return re.sub(r"(?ms)^\s*```.*?^\s*```[^\n]*$", " ", body)


def anchor_tokens(text: str) -> set[str]:
    """Tokens a claim's cited lines should contain: identifier parts of 4+ characters and numbers of 2+
    digits from its backticked spans."""
    out: set[str] = set()
    for t in re.findall(r"`([^`\n]{2,80})`", text):
        out |= {p for p in re.split(r"[^\w]+", t) if len(p) >= 4 and not p.isdigit()}
        out |= set(re.findall(r"\b\d{2,}\b", t))
    return out


def anchor_status(repo: Path, refs: list[str], text: str, pad: int = 5) -> bool | None:
    """True when some backticked token of the claim occurs in the lines its refs point at (+/- pad);
    False when none does; None when there is nothing to check (no refs or no tokens). A directory, a
    doc file, a symbol naming no definition, and a bare path to a file over 200 lines give no lines."""
    toks = anchor_tokens(text)
    if not toks or not refs:
        return None
    window: list[str] = []
    for r in refs:
        rp = ref_path(r)
        if rp.endswith(DOC_SUFFIXES) or "/docs/" in "/" + rp:
            continue
        sp = ref_span(repo, r)
        if sp is None:
            ls = repo_lines(repo, rp) if "::" not in r and (repo / rp).is_file() else []
            if 0 < len(ls) <= 200:
                window += ls
            continue
        path, a, b = sp
        ls = repo_lines(repo, path)
        window += ls[max(0, a - 1 - pad):min(len(ls), b + pad)]
    w = "\n".join(window)
    return any(re.search(r"(?<!\w)" + re.escape(x) + r"(?!\w)", w) or (len(x) >= 6 and x in w) for x in toks)
