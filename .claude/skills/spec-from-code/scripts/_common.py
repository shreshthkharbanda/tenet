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
    r"(?P<refs>(?:`[^`\n]+`\s*(?:,\s*)?)*)"
    r"(?P<text>\S.*)$"
)
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
    section = ""
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            continue
        m = CLAIM_RE.match(line)
        if not m:
            continue
        refs = [r.strip() for r in REF_RE.findall(m.group("refs") or "")]
        claims.append({
            "id": m.group("id"),
            "confidence": m.group("conf"),
            "refs": refs,
            "text": m.group("text").strip(),
            "line": n,
            "section": section,
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
    m = re.match(r"^(.+?):(\d+)(?:-(\d+))?$", ref)
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
    m = re.match(r"^(.+?):(\d+)(?:-(\d+))?$", ref)
    return m.group(1) if m else ref


def rel(p: Path, root: Path) -> str:
    return os.path.relpath(p, root).replace(os.sep, "/")
