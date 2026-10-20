#!/usr/bin/env python3
"""Gate G8: chapter stories (references/story.md). A story is the readable layer over a module's
claims; it may select, order, connect and illustrate, never add. This parses `_meta/story/<module>.md`
and checks that every paragraph, row and figure element cites claims that exist, that every literal and
number it states is in a cited claim or the code that claim cites, and the length and shape rules.

  check_story.py <specs> [--module ID ...] [--repo ROOT]
Writes _meta/story/<module>.check.json. Exit 1 on any error.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import XREF_RE, eprint, parse_claims, parse_frontmatter, read_json, ref_path, write_json

RANGE_RE = re.compile(r"\[([A-Z][A-Z0-9]{1,11})-(\d{3,4})\]-\[([A-Z][A-Z0-9]{1,11})-(\d{3,4})\]")
CODE_RE = re.compile(r"`([^`\n]+)`")
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|\d+(?:\.\d+)?")
NUM = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w-])")
ROW = re.compile(r"^\|(.*)\|\s*$")
CONDITIONAL = re.compile(r"^(When|If|Unless|Where|While|Once)\b")
VERB_HINT = re.compile(r"\b(is|are|was|were|has|have|does|do|can|cannot|never|always|only|keeps?|sees?|sits?|"
                       r"goes|gets?|runs?|writes?|reads?|picks?|skips?|stops?|starts?|holds?|wins?|loses?|fails?|"
                       r"counts?|decides?|returns?|raises?|rejects?|sends?|uses?|makes?|takes?|leaves?|stays?|"
                       r"becomes?|moves?|falls?|retries|tries|waits?|comes?|lives?|owns?|turns?|blocks?|"
                       r"benches|cools?|resolves?|filters?|applies|binds?|reaches?|follows?|shares?)\b", re.I)
MAX_SENT, MAX_PARA, MAX_NODES = 32, 120, 12


def expand_ids(md: str) -> list[str]:
    """Claim IDs a piece of story text cites; a range [A-010]-[A-014] cites every ID in it."""
    ids = []
    for m in RANGE_RE.finditer(md):
        if m.group(1) == m.group(3):
            w = len(m.group(2))
            ids += [f"{m.group(1)}-{n:0{w}d}" for n in range(int(m.group(2)), int(m.group(4)) + 1)]
    return list(dict.fromkeys(ids + XREF_RE.findall(md)))


def cell_ids(cell: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[A-Z][A-Z0-9]{1,11}-\d{3,4}", cell)))


def words(md: str) -> int:
    return len(re.sub(r"\[[A-Z][A-Z0-9-]+\]", " ", CODE_RE.sub(" x ", md)).split())


def sentences(md: str) -> list[str]:
    """Split prose into sentences without breaking inside code spans or common abbreviations."""
    keep: list[str] = []

    def mask(m):
        keep.append(m.group(0))
        return f"\x00{len(keep) - 1}\x00"

    masked = CODE_RE.sub(mask, md)
    masked = re.sub(r"\b(e\.g|i\.e|etc|vs)\.", lambda m: m.group(1) + "\x01", masked)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z`\[(\x00\"])", masked)
    out = []
    for p in parts:
        p = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], p).replace("\x01", ".")
        if p.strip():
            out.append(p.strip())
    return out


def literal_tokens(md: str) -> set[str]:
    """Names and numbers a sentence states: tokens of its code spans plus bare numbers."""
    text = re.sub(r"\[?[A-Z][A-Z0-9]{1,11}-\d{3,4}\]?", " ", md)
    toks = set()
    for lit in CODE_RE.findall(text):
        toks |= set(TOKEN.findall(re.sub(r"<[^>]*>", " ", lit)))
    toks |= set(NUM.findall(CODE_RE.sub(" ", text)))
    return toks


def parse_story(text: str) -> tuple[dict, list[str]]:
    """Story markdown -> structure. Returns (story, parse errors)."""
    fm, body = parse_frontmatter(text)
    errs: list[str] = []
    st = {"module": fm.get("module"), "headline": "", "minute": [], "glance": None, "sections": [], "watch": [], "words": 0}
    lines = body.splitlines()
    i, cur, mode, para = 0, None, None, []

    def flush():
        nonlocal para
        if para:
            txt = " ".join(x.strip() for x in para)
            if mode == "minute":
                st["minute"].append(txt)
            elif cur is not None:
                cur["blocks"].append({"t": "p", "md": txt})
            para = []

    while i < len(lines):
        ln, s = lines[i], lines[i].strip()
        if s.startswith("# ") and not s.startswith("## "):
            flush(); st["headline"] = s[2:].strip(); mode = None; i += 1; continue
        if s == "@minute":
            flush(); mode = "minute"; i += 1; continue
        if s.startswith("## "):
            flush(); title = s[3:].strip(); mode = None
            if title.lower() == "at a glance":
                mode, cur = "glance", None
                st["glance"] = {"rows": []}
            elif title.lower() == "watch out":
                mode, cur = "watch", None
            else:
                cur = {"title": title, "blocks": []}
                st["sections"].append(cur)
            i += 1; continue
        if s.startswith("@figure"):
            flush()
            m = re.match(r'@figure\s+(flow|states|sequence)\s+id=([\w-]+)\s+title="([^"]*)"\s*$', s)
            fig = {"t": "fig", "kind": m.group(1) if m else "?", "id": m.group(2) if m else "?",
                   "title": m.group(3) if m else "", "nodes": [], "edges": [], "actors": [], "steps": [], "line": i + 1}
            if not m:
                errs.append(f"line {i + 1}: figure header must be @figure flow|states|sequence id=<id> title=\"...\"")
            i += 1
            while i < len(lines) and ROW.match(lines[i].strip()):
                c = [x.strip() for x in re.split(r"(?<!\\)\|", lines[i].strip().strip("|"))]
                head = c[0]
                mm = re.match(r"^(node|state|actor)\s+([\w-]+)$", head)
                em = re.match(r"^([\w-]+)\s*>\s*([\w-]+)$", head)
                if mm and len(c) >= 2:
                    rec = {"id": mm.group(2), "label": c[1], "ids": cell_ids(c[2]) if len(c) > 2 else []}
                    (fig["actors"] if mm.group(1) == "actor" else fig["nodes"]).append(rec)
                elif em and len(c) >= 3:
                    fig["edges"].append({"a": em.group(1), "b": em.group(2), "label": c[1], "ids": cell_ids(c[2])})
                else:
                    errs.append(f"line {i + 1}: figure row not understood: {lines[i].strip()[:80]}")
                i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip().startswith("@steps"):
                i += 1
                while i < len(lines) and ROW.match(lines[i].strip()):
                    c = [x.strip() for x in re.split(r"(?<!\\)\|", lines[i].strip().strip("|"))]
                    if len(c) >= 3:
                        fig["steps"].append({"target": c[0].replace(" ", ""), "title": c[1], "md": c[2], "ids": expand_ids(c[2])})
                    else:
                        errs.append(f"line {i + 1}: step row needs | target | title | text |")
                    i += 1
            if cur is None:
                errs.append(f"line {fig['line']}: a figure must sit inside a ## section")
            else:
                cur["blocks"].append(fig)
            continue
        if mode == "glance" and ROW.match(s):
            c = [x.strip() for x in re.split(r"(?<!\\)\|", s.strip("|"))]
            if not re.match(r"^:?-{2,}", c[0]) and c[0].lower() != "when":
                if len(c) < 3:
                    errs.append(f"line {i + 1}: at-a-glance rows need | When | Then | Claims |")
                else:
                    st["glance"]["rows"].append({"when": c[0], "then": c[1], "ids": cell_ids(c[2])})
            i += 1; continue
        bm = re.match(r"^\s*[-*]\s+(.*)$", ln)
        if bm:
            flush()
            item = bm.group(1).strip()
            while i + 1 < len(lines) and lines[i + 1].startswith("  ") and lines[i + 1].strip() and not re.match(r"^\s*[-*]\s", lines[i + 1]):
                i += 1
                item += " " + lines[i].strip()
            if mode == "watch":
                st["watch"].append(item)
            elif cur is not None:
                if cur["blocks"] and cur["blocks"][-1]["t"] == "ul":
                    cur["blocks"][-1]["items"].append(item)
                else:
                    cur["blocks"].append({"t": "ul", "items": [item]})
            i += 1; continue
        if not s:
            flush()
        elif mode in ("minute", None) or cur is not None:
            if mode == "glance":
                errs.append(f"line {i + 1}: only the table belongs under At a glance")
            elif mode == "watch":
                errs.append(f"line {i + 1}: Watch out holds bullets only")
            else:
                para.append(ln)
        i += 1
    flush()
    prose = st["minute"] + [b["md"] for s_ in st["sections"] for b in s_["blocks"] if b["t"] == "p"] \
        + [x for s_ in st["sections"] for b in s_["blocks"] if b["t"] == "ul" for x in b["items"]] + st["watch"] \
        + [r["when"] + " " + r["then"] for r in (st["glance"] or {}).get("rows", [])]
    st["words"] = sum(words(x) for x in prose)
    return st, errs


class Checker:
    def __init__(self, specs: Path, repo: Path):
        self.specs, self.repo = specs, repo
        self.claims: dict[str, dict] = {}
        self.module_of: dict[str, str] = {}
        for fp in sorted(specs.glob("modules/*.md")) + sorted(specs.glob("0*.md")):
            fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
            for c in parse_claims(body):
                self.claims[c["id"]] = c
                self.module_of[c["id"]] = fm.get("module") or fp.stem
        self._src: dict[str, str] = {}

    def code_of(self, ids) -> str:
        out = []
        for cid in ids:
            for r in self.claims.get(cid, {}).get("refs", []):
                p = ref_path(r)
                if p not in self._src:
                    f = self.repo / p
                    self._src[p] = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
                out.append(self._src[p])
        return "\n".join(out)

    def unsupported(self, md: str, ids: list[str]) -> list[str]:
        """Tokens stated in md that neither the cited claims' text nor their code contains."""
        toks = literal_tokens(md)
        if not toks:
            return []
        said = " ".join(self.claims[x]["text"] for x in ids if x in self.claims)
        code = None
        miss = []
        for t in sorted(toks):
            if t.lower() in said.lower():
                continue
            code = self.code_of(ids) if code is None else code
            if t not in code:
                miss.append(t)
        return miss

    def check(self, module: str, text: str) -> dict:
        st, errors = parse_story(text)
        warnings: list[str] = []
        where = lambda s: s[:70] + ("…" if len(s) > 70 else "")
        mod_claims = [c for cid, c in self.claims.items() if self.module_of[cid] == module]
        if not st["headline"]:
            errors.append("no # headline")
        elif len(st["headline"].split()) > 14:
            errors.append(f"headline over 14 words: {where(st['headline'])}")
        if not st["minute"]:
            errors.append("no @minute summary")
        else:
            mw = sum(words(p) for p in st["minute"])
            mids = {x for p in st["minute"] for x in expand_ids(p)}
            if mw > 120:
                errors.append(f"@minute is {mw} words (at most 120)")
            if len(mids) < 3:
                errors.append(f"@minute cites {len(mids)} claims (at least 3)")
        cited: set[str] = set()

        def prose(md: str, what: str):
            ids = expand_ids(md)
            if not ids:
                errors.append(f"{what} cites no claim: {where(md)}")
            if words(md) > MAX_PARA:
                errors.append(f"{what} is {words(md)} words (at most {MAX_PARA}): {where(md)}")
            for s in sentences(md):
                sid = expand_ids(s)
                if words(s) > MAX_SENT:
                    errors.append(f"sentence of {words(s)} words (at most {MAX_SENT}): {where(s)}")
                if literal_tokens(s) and not sid:
                    errors.append(f"sentence states a literal or number but cites no claim: {where(s)}")
                miss = self.unsupported(s, sid or ids)
                if miss:
                    errors.append(f"states {', '.join(miss[:3])} found in neither the cited claims nor their code: {where(s)}")
            cited.update(ids)

        for k, p in enumerate(st["minute"]):
            prose(p, "minute paragraph")
        conditional = sum(bool(CONDITIONAL.match(c["text"])) for c in mod_claims)
        g = st["glance"]
        if g is None and conditional >= 5:
            errors.append(f"no At a glance table, and the module has {conditional} conditional claims")
        if g is not None:
            if not 3 <= len(g["rows"]) <= 14:
                (errors if len(g["rows"]) < 3 else warnings).append(f"At a glance has {len(g['rows'])} rows (3 to 14)")
            for r in g["rows"]:
                if not r["ids"]:
                    errors.append(f"at-a-glance row cites no claim: {where(r['when'])}")
                for x in r["ids"]:
                    if x not in self.claims:
                        errors.append(f"at-a-glance row cites unknown claim {x}")
                miss = self.unsupported(r["when"] + " " + r["then"], [x for x in r["ids"] if x in self.claims])
                if miss:
                    errors.append(f"at-a-glance row states {', '.join(miss[:3])} found in neither its claims nor their code: {where(r['when'])}")
                cited.update(r["ids"])
        if not 3 <= len(st["sections"]) <= 6:
            (errors if len(st["sections"]) < 2 else warnings).append(f"{len(st['sections'])} story sections (3 to 6)")
        for sec in st["sections"]:
            if len(sec["title"].split()) < 4 or not VERB_HINT.search(sec["title"]):
                warnings.append(f"heading reads as a label, not an assertion: {sec['title']}")
            figs = [b for b in sec["blocks"] if b["t"] == "fig"]
            if len(figs) > 1:
                errors.append(f"section '{where(sec['title'])}' has {len(figs)} figures (at most 1)")
            for b in sec["blocks"]:
                if b["t"] == "p":
                    prose(b["md"], "paragraph")
                elif b["t"] == "ul":
                    for it in b["items"]:
                        prose(it, "bullet")
                elif b["t"] == "fig":
                    self.check_figure(b, errors, warnings, cited)
        if not st["watch"]:
            errors.append("no Watch out bullets")
        for it in st["watch"]:
            prose(it, "watch-out bullet")
        for x in sorted(cited):
            if x not in self.claims:
                errors.append(f"cites unknown claim {x}")
        defects = [c["id"] for c in mod_claims if c["section"].lower().startswith("suspected defect")]
        if defects and not set(defects) & cited:
            warnings.append(f"cites none of the module's {len(defects)} suspected defects")
        if not 700 <= st["words"] <= 1800:
            warnings.append(f"story is {st['words']} words (700 to 1,800)")
        subs = {(c["section"], c["subsection"]) for c in mod_claims if c["subsection"]}
        hit = {(self.claims[x]["section"], self.claims[x]["subsection"]) for x in cited if x in self.claims and self.module_of[x] == module}
        coverage = len(subs & hit) / len(subs) if subs else 1.0
        if coverage < 0.5:
            warnings.append(f"chips reach {coverage:.0%} of the module's subsections")
        return {"module": module, "errors": errors, "warnings": warnings, "story": st,
                "stats": {"words": st["words"], "claims_cited": len(cited), "coverage": round(coverage, 3),
                          "figures": sum(b["t"] == "fig" for s_ in st["sections"] for b in s_["blocks"])}}

    def check_figure(self, f: dict, errors: list, warnings: list, cited: set):
        name = f"figure {f['id']}"
        elems = f["nodes"] if f["kind"] != "sequence" else f["actors"]
        ids = {e["id"] for e in elems}
        if f["kind"] == "sequence" and not f["actors"]:
            errors.append(f"{name}: a sequence needs actor rows")
        if len(elems) > MAX_NODES:
            errors.append(f"{name}: {len(elems)} nodes (at most {MAX_NODES}; split it into an overview and a detail)")
        if not f["edges"]:
            errors.append(f"{name}: no edges or messages")
        for n in (f["nodes"] if f["kind"] != "sequence" else []):
            if not n["ids"]:
                errors.append(f"{name}: node {n['id']} cites no claim")
            if len(n["label"].split()) > 5:
                errors.append(f"{name}: node label over 5 words: {n['label']}")
            miss = self.unsupported(n["label"], n["ids"])
            if miss:
                errors.append(f"{name}: node {n['id']} states {', '.join(miss[:3])} found in neither its claims nor their code")
            cited.update(n["ids"])
        for e in f["edges"]:
            for end in (e["a"], e["b"]):
                if end not in ids:
                    errors.append(f"{name}: edge {e['a']}>{e['b']} names an undeclared {end}")
            if not e["ids"]:
                errors.append(f"{name}: edge {e['a']}>{e['b']} cites no claim")
            if len(e["label"].split()) > 5:
                warnings.append(f"{name}: edge label over 5 words: {e['label']}")
            miss = self.unsupported(e["label"], e["ids"])
            if miss:
                errors.append(f"{name}: edge {e['a']}>{e['b']} states {', '.join(miss[:3])} found in neither its claims nor their code")
            cited.update(e["ids"])
        targets = ids | {f"{e['a']}>{e['b']}" for e in f["edges"]}
        if f["steps"] and not 2 <= len(f["steps"]) <= 8:
            warnings.append(f"{name}: {len(f['steps'])} steps (2 to 8)")
        for s in f["steps"]:
            if s["target"] not in targets:
                errors.append(f"{name}: step '{s['title']}' targets {s['target']}, which is not in the figure")
            if not s["ids"]:
                errors.append(f"{name}: step '{s['title']}' cites no claim")
            miss = self.unsupported(s["md"], s["ids"])
            if miss:
                errors.append(f"{name}: step '{s['title']}' states {', '.join(miss[:3])} found in neither its claims nor their code")
            cited.update(s["ids"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--repo", default=None)
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    run = read_json(specs / "_meta" / "run.json") if (specs / "_meta" / "run.json").exists() else {}
    repo = Path(a.repo or run.get("repo") or ".").resolve()
    sdir = specs / "_meta" / "story"
    files = sorted(sdir.glob("*.md")) if sdir.exists() else []
    if a.module:
        files = [f for f in files if f.stem in a.module]
        for m in set(a.module) - {f.stem for f in files}:
            eprint(f"ERROR: {m}: no story at _meta/story/{m}.md")
    ck = Checker(specs, repo)
    bad = 0
    for f in files:
        r = ck.check(f.stem, f.read_text(encoding="utf-8", errors="replace"))
        write_json(sdir / f"{f.stem}.check.json", {k: v for k, v in r.items() if k != "story"})
        for w in r["warnings"]:
            eprint(f"WARN: {f.stem}: {w}")
        for e in r["errors"][:60]:
            eprint(f"ERROR: {f.stem}: {e}")
        s = r["stats"]
        eprint(f"{f.stem}: {len(r['errors'])} errors, {len(r['warnings'])} warnings; {s['words']} words, {s['claims_cited']} claims "
               f"cited, {s['figures']} figures, subsection coverage {s['coverage']:.0%}")
        bad += bool(r["errors"])
    if not files:
        eprint("no stories under _meta/story/")
    return 1 if bad or (a.module and len(files) < len(a.module)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
