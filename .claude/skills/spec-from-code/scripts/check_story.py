#!/usr/bin/env python3
"""Gate G8: stories (references/story.md) held to the readability standard (references/readability.md).

A story is the readable layer over the claims: it may select, order, connect and illustrate, never
add. It is written in layers: an Everyone layer with no code at all (headline, "In plain words",
headings, figures, the example timeline, Watch out), an Engineer layer whose few exact names are each
bridged to a plain term in "Words you'll see", and the ledger below it for experts. This checks:
- evidence: every paragraph, row, bullet and figure element cites claims that exist; every literal
  and number is in a cited claim or the code it cites;
- layers: no code formatting or identifier anywhere in the Everyone layer; every code name in the
  Engineer layer defined in "Words you'll see"; code density limits;
- reading: sentence and paragraph length, plain-words length and grade level, acronyms defined,
  passive voice (warning);
- shape: headline, sections, figures (plain labels, at most 12 nodes, steps that target real parts),
  the system story's walkthrough steps matching each main path.

  check_story.py <specs> [--module ID ...] [--repo ROOT]
Module stories are _meta/story/<module>.md; the system story is _meta/story/_system.md.
Writes _meta/story/<name>.check.json. Exit 1 on any error.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import XREF_RE, eprint, parse_claims, parse_frontmatter, read_json, ref_path, write_json

RANGE_RE = re.compile(r"\[([A-Z][A-Z0-9]{1,11})-(\d{3,4})\]-\[([A-Z][A-Z0-9]{1,11})-(\d{3,4})\]")
CHIP_RE = re.compile(r"\[[A-Z][A-Z0-9]{1,11}-\d{3,4}\](?:-\[[A-Z][A-Z0-9]{1,11}-\d{3,4}\])?")
CODE_RE = re.compile(r"`([^`\n]+)`")
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|\d+(?:\.\d+)?")
NUM = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w-])")
ROW = re.compile(r"^\|(.*)\|\s*$")
CONDITIONAL = re.compile(r"^(When|If|Unless|Where|While|Once)\b")
# an identifier: snake_case, dotted.name, camelCase/PascalCase with an inner capital, or a call
IDENT = re.compile(r"(?<![\w`])(?:[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+|[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*|[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*"
                   r"|[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]+|[A-Za-z_][A-Za-z0-9_]*\(\))(?![\w`])")
ACRONYM = re.compile(r"(?<![\w-])([A-Z]{2,6})s?(?![\w-])")
# programming words a reader of the Everyone layer stumbles on (L78): each needs a plain row in Words you'll see
JARGON = ("async", "asynchronous", "sync", "synchronous", "pipeline", "callback", "hook", "wildcard", "callable", "picker",
          "plugin", "middleware", "coroutine", "singleton", "schema", "enum", "boolean", "regex", "mutex", "payload",
          "namespace", "serialize", "serialized", "deserialize", "runtime", "thread", "lock", "semaphore", "flag")
QUOTE = re.compile(r'"([^"\n]{20,})"')
UNIVERSAL = {"API", "APIs", "HTTP", "HTTPS", "URL", "ID", "IDs", "AI", "CPU", "UTC", "OK", "JSON", "CEO", "CTO", "IP", "US", "UK", "PDF"}
VALUE = re.compile(r"^(?:-?\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds?|minutes?|min|h|hours?|%|x|KB|MB)?|\"[^\"]*\"|'[^']*'|\d{3}(?:\s+[A-Z][\w ]+)?)$")
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ed|built|chosen|done|given|held|kept|known|left|made|"
                     r"put|read|run|seen|sent|set|shown|taken|thrown|told|written|found|lost|bound|paid|spent)\b", re.I)
VERB_HINT = re.compile(r"\b(is|are|was|were|has|have|does|do|can|cannot|never|always|only|keeps?|sees?|sits?|"
                       r"goes|gets?|runs?|writes?|reads?|picks?|skips?|stops?|starts?|holds?|wins?|loses?|fails?|"
                       r"counts?|decides?|returns?|raises?|rejects?|sends?|uses?|makes?|takes?|leaves?|stays?|"
                       r"becomes?|moves?|falls?|retries|tries|waits?|comes?|lives?|owns?|turns?|blocks?|"
                       r"benches|cools?|resolves?|filters?|applies|binds?|reaches?|follows?|shares?|lands?|lapses?|"
                       r"answers?|chooses?|drops?|reports?|reserves?|refunds?|limits?|caps?|admits?|walks?|marks?|"
                       r"protects?|lets?|needs?|serves?|routes?|matches?|tells?|knows?|breaks?|survives?)\b", re.I)
MAX_SENT, MAX_PARA, MAX_NODES = 32, 120, 12
PLAIN_MIN, PLAIN_MAX, PLAIN_AVG, PLAIN_SENT = 50, 130, 18, 26
ENG_AVG, CODE_PER_100, CODE_PER_100_ERR, MINUTE_CODE = 22, 4, 6, 3
UNIT_S = {"ms": 0.001, "s": 1, "sec": 1, "second": 1, "seconds": 1, "min": 60, "minute": 60, "minutes": 60, "m": 60,
          "h": 3600, "hour": 3600, "hours": 3600}


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


def strip_chips(md: str) -> str:
    return re.sub(r"\s*,?\s*" + CHIP_RE.pattern, "", md)


def words(md: str) -> int:
    return len(strip_chips(CODE_RE.sub(" x ", md)).split())


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


def identifiers(md: str) -> list[str]:
    """Code names written outside code formatting (the Everyone layer may contain none at all)."""
    text = CODE_RE.sub(" ", strip_chips(md))
    text = re.sub(r"\b(?:e\.g|i\.e)\.", " ", text)
    return [m.group(0) for m in IDENT.finditer(text) if not re.fullmatch(r"\d+(\.\d+)*", m.group(0))]


def syllables(w: str) -> int:
    w = w.lower().strip(".,;:!?()\"'")
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def grade(md: str) -> float:
    """Flesch-Kincaid grade of plain text (code and chips removed). A tripwire, not a target."""
    sents = sentences(md)
    text = strip_chips(CODE_RE.sub(" ", md))
    ws = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if not ws or not sents:
        return 0.0
    return round(0.39 * len(ws) / len(sents) + 11.8 * sum(syllables(w) for w in ws) / len(ws) - 15.59, 1)


def seconds(t: str) -> float | None:
    m = re.match(r"^\s*(?:t\s*=\s*)?(\d+(?:\.\d+)?)\s*([a-z]*)\s*$", t.strip().lower())
    if not m:
        return None
    unit = m.group(2) or "s"
    return float(m.group(1)) * UNIT_S[unit] if unit in UNIT_S else None


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def flow_id(title: str) -> str:
    sl = slug(title)
    return "flow-" + (sl if len(sl) <= 48 else sl[:48].rsplit("-", 1)[0])


def overview_flows(specs: Path) -> dict[str, int]:
    """Main paths of the overview: flow id -> number of steps (the reader site's walkthroughs)."""
    ov = next((f for f in sorted(specs.glob("0*.md"))
               if parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))[0].get("kind") == "overview"), None)
    if not ov:
        return {}
    out, cur, in_paths = {}, None, False
    for ln in parse_frontmatter(ov.read_text(encoding="utf-8", errors="replace"))[1].splitlines():
        if ln.startswith("## "):
            in_paths = ln[3:].strip().lower().startswith("main path")
            cur = None
        elif ln.startswith("### ") and in_paths:
            cur = flow_id(re.sub(r"^\d+\.\s*", "", ln[4:].strip()))
            out[cur] = 0
        elif cur and re.match(r"^\d+\.\s+", ln.strip()):
            out[cur] += 1
    return out


def block_layer(b: dict) -> str:
    """The one definition of the layer a section block belongs to: a section's lead, its figures and its
    paths are Everyone; the rest of its prose is Engineer. The reader site (site_data tags each block)
    and the persona snapshot (story_probe) both read it, so a persona reader is tested on exactly what an
    Everyone reader sees (L77)."""
    return "engineer" if b["t"] == "ul" or (b["t"] == "p" and not b.get("lead")) else "everyone"


def parse_story(text: str) -> tuple[dict, list[str]]:
    """Story markdown -> structure. Returns (story, parse errors)."""
    fm, body = parse_frontmatter(text)
    errs: list[str] = []
    st = {"module": fm.get("module"), "headline": "", "plain": [], "minute": [], "words_table": [], "glance": None,
          "sections": [], "watch": [], "words": 0}
    lines = body.splitlines()
    i, cur, mode, para = 0, None, None, []

    def cells(s):
        return [x.strip() for x in re.split(r"(?<!\\)\|", s.strip().strip("|"))]

    def flush():
        nonlocal para
        if para:
            txt = " ".join(x.strip() for x in para)
            if mode in ("minute", "plain"):
                st[mode].append(txt)
            elif cur is not None:
                cur["blocks"].append({"t": "p", "md": txt})
            para = []

    while i < len(lines):
        ln, s = lines[i], lines[i].strip()
        if s.startswith("# ") and not s.startswith("## "):
            flush(); st["headline"] = s[2:].strip(); mode = None; i += 1; continue
        if s in ("@minute", "@plain"):
            flush(); mode = s[1:]; i += 1; continue
        if s.startswith("## "):
            flush(); title = s[3:].strip(); mode = None
            low = title.lower().replace("’", "'")
            if low == "at a glance":
                mode, cur = "glance", None
                st["glance"] = {"rows": []}
            elif low == "watch out":
                mode, cur = "watch", None
            elif low in ("words you'll see", "words you will see"):
                mode, cur = "words", None
            else:
                cur = {"title": title, "blocks": []}
                st["sections"].append(cur)
            i += 1; continue
        if s.startswith("@path"):
            flush()
            m = re.match(r"@path\s+([\w-]+)\s*$", s)
            blk = {"t": "path", "flow": m.group(1) if m else "?", "steps": [], "line": i + 1}
            if not m:
                errs.append(f"line {i + 1}: path header must be @path <flow-id>")
            i += 1
            while i < len(lines) and ROW.match(lines[i].strip()):
                c = cells(lines[i])
                if len(c) >= 2 and c[0].isdigit():
                    blk["steps"].append({"n": int(c[0]), "md": c[1]})
                elif not re.match(r"^:?-{2,}", c[0]) and c[0].lower() not in ("step", "#"):
                    errs.append(f"line {i + 1}: path rows are | <step number> | <plain text with chips> |")
                i += 1
            if cur is None:
                errs.append(f"line {blk['line']}: a path must sit inside a ## section")
            else:
                cur["blocks"].append(blk)
            continue
        if s.startswith("@figure"):
            flush()
            m = re.match(r'@figure\s+(flow|states|sequence|timeline)\s+id=([\w-]+)\s+title="([^"]*)"\s*$', s)
            fig = {"t": "fig", "kind": m.group(1) if m else "?", "id": m.group(2) if m else "?",
                   "title": m.group(3) if m else "", "nodes": [], "edges": [], "actors": [], "lanes": [], "events": [],
                   "steps": [], "line": i + 1}
            if not m:
                errs.append(f"line {i + 1}: figure header must be @figure flow|states|sequence|timeline id=<id> title=\"...\"")
            i += 1
            while i < len(lines) and ROW.match(lines[i].strip()):
                c = cells(lines[i])
                head = c[0]
                mm = re.match(r"^(node|state|actor|lane)\s+([\w-]+)$", head)
                em = re.match(r"^([\w-]+)\s*>\s*([\w-]+)$", head)
                if mm and len(c) >= 2:
                    rec = {"id": mm.group(2), "label": c[1], "ids": cell_ids(c[2]) if len(c) > 2 else []}
                    {"actor": fig["actors"], "lane": fig["lanes"]}.get(mm.group(1), fig["nodes"]).append(rec)
                elif fig["kind"] == "timeline" and len(c) >= 5 and seconds(c[0]) is not None:
                    fig["events"].append({"time": c[0], "t": seconds(c[0]), "lane": c[1], "label": c[2], "state": c[3],
                                          "ids": cell_ids(c[4])})
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
                    c = cells(lines[i])
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
        if mode in ("glance", "words") and ROW.match(s):
            c = cells(s)
            if not re.match(r"^:?-{2,}", c[0]) and c[0].lower() not in ("when", "term"):
                if mode == "glance":
                    if len(c) < 3:
                        errs.append(f"line {i + 1}: at-a-glance rows need | When | Then | Claims |")
                    else:
                        st["glance"]["rows"].append({"when": c[0], "then": c[1], "ids": cell_ids(c[2])})
                else:
                    if len(c) < 4:
                        errs.append(f"line {i + 1}: word rows need | Term | Means | In the code | Claims |")
                    else:
                        st["words_table"].append({"term": c[0], "means": c[1], "code": c[2], "ids": cell_ids(c[3]),
                                                  "names": [x.strip() for x in CODE_RE.findall(c[2])]})
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
        elif mode in ("minute", "plain", None) or cur is not None:
            if mode in ("glance", "words"):
                errs.append(f"line {i + 1}: only the table belongs under this heading")
            elif mode == "watch":
                errs.append(f"line {i + 1}: Watch out holds bullets only")
            else:
                para.append(ln)
        i += 1
    flush()
    for s_ in st["sections"]:  # a section's first paragraph is its lead (block_layer)
        if s_["blocks"] and s_["blocks"][0]["t"] == "p":
            s_["blocks"][0]["lead"] = True
    prose = st["plain"] + st["minute"] + [b["md"] for s_ in st["sections"] for b in s_["blocks"] if b["t"] == "p"] \
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
        self.flows = overview_flows(specs)

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
        said = " ".join(self.claims[x]["text"] + " " + " ".join(self.claims[x].get("detail", [])) for x in ids if x in self.claims)
        code = None
        miss = []
        for t in sorted(toks):
            if t.lower() in said.lower():
                continue
            code = self.code_of(ids) if code is None else code
            if t not in code:
                miss.append(t)
        return miss

    def partial_quote(self, md: str, ids: list[str]) -> str:
        """The rest of a quoted message when md quotes only its start (L78: a cut message reads as the whole one)."""
        said = [q.strip() for x in ids if x in self.claims
                for q in QUOTE.findall(self.claims[x]["text"] + " " + " ".join(self.claims[x].get("detail", [])))]
        for q in QUOTE.findall(md):
            q = q.strip()
            if not said or q in said:
                continue
            longer = [m for m in said if m.startswith(q.rstrip(".")) and len(m) > len(q) + 3]
            if longer:
                return longer[0][len(q.rstrip(".")):].lstrip(" .")
        return ""

    def check(self, module: str, text: str) -> dict:
        st, errors = parse_story(text)
        warnings: list[str] = []
        system = module == "_system"
        where = lambda s: s[:70] + ("…" if len(s) > 70 else "")
        mod_claims = [c for cid, c in self.claims.items() if self.module_of[cid] == module]
        cited: set[str] = set()
        defined = {n for r in st["words_table"] for n in r["names"]}
        defined_terms = {r["term"].lower() for r in st["words_table"]}
        everyone_text: list[str] = []
        eng_words = eng_code = 0
        sent_lengths: list[int] = []
        passive = total_sent = 0

        def evidence(md: str, what: str, ids_fallback=None):
            ids = expand_ids(md)
            if not ids and not ids_fallback:
                errors.append(f"{what} cites no claim: {where(md)}")
            for s in sentences(md):
                sid = expand_ids(s)
                if not sid and not ids_fallback:
                    # a story judge labels an uncited sentence unsupported, so the gate asks for the chip (L78)
                    errors.append(f"sentence cites no claim (end every sentence with the chips it rests on): {where(s)}")
                miss = self.unsupported(s, sid or ids or ids_fallback or [])
                if miss:
                    errors.append(f"states {', '.join(miss[:3])} found in neither the cited claims nor their code: {where(s)}")
                part = self.partial_quote(s, sid or ids or ids_fallback or [])
                if part:
                    errors.append(f"quotes part of a message as if it were whole; the claim's message goes on "
                                  f"('…{part[:40]}'): quote it whole or say it in words: {where(s)}")
            cited.update(ids)

        def everyone(md: str, what: str, max_sent: int = MAX_SENT):
            """Everyone layer: no code formatting, no identifiers."""
            nonlocal passive, total_sent
            everyone_text.append(md)
            if CODE_RE.search(md):
                errors.append(f"{what} uses code formatting ({CODE_RE.search(md).group(0)}); the Everyone layer has none: {where(md)}")
            ids_ = identifiers(md)
            if ids_:
                errors.append(f"{what} uses the code name {ids_[0]}; say it in plain words (the Everyone layer has no code): {where(md)}")
            for s in sentences(md):
                n = words(s)
                total_sent += 1
                passive += bool(PASSIVE.search(s))
                if n > max_sent:
                    errors.append(f"sentence of {n} words (at most {max_sent} here): {where(s)}")

        def engineer(md: str, what: str):
            """Engineer layer: few code spans, each a value or defined in Words you'll see."""
            nonlocal eng_words, eng_code, passive, total_sent
            if words(md) > MAX_PARA:
                errors.append(f"{what} is {words(md)} words (at most {MAX_PARA}): {where(md)}")
            spans = CODE_RE.findall(md)
            eng_words += words(md)
            eng_code += len(spans)
            for sp in spans:
                if not VALUE.match(sp.strip()) and sp.strip() not in defined:
                    errors.append(f"code name `{sp}` is not defined in Words you'll see (add a row: plain term, meaning, this name): {where(md)}")
            ids_ = identifiers(md)
            if ids_:
                errors.append(f"{what} writes the code name {ids_[0]} without code formatting; format it and define it: {where(md)}")
            for s in sentences(md):
                n = words(s)
                sent_lengths.append(n)
                total_sent += 1
                passive += bool(PASSIVE.search(s))
                if n > MAX_SENT:
                    errors.append(f"sentence of {n} words (at most {MAX_SENT}): {where(s)}")

        # headline and plain words: the Everyone layer
        if not st["headline"]:
            errors.append("no # headline")
        else:
            everyone(st["headline"], "headline")
            if len(st["headline"].split()) > 14:
                errors.append(f"headline over 14 words: {where(st['headline'])}")
        if not st["plain"]:
            errors.append("no @plain summary (In plain words: the whole chapter for anyone, with no code)")
        else:
            pw = sum(words(p) for p in st["plain"])
            pids = {x for p in st["plain"] for x in expand_ids(p)}
            ss = [words(s) for p in st["plain"] for s in sentences(p)]
            avg = sum(ss) / len(ss) if ss else 0
            g = grade(" ".join(st["plain"]))
            if not PLAIN_MIN <= pw <= PLAIN_MAX:
                errors.append(f"In plain words is {pw} words ({PLAIN_MIN} to {PLAIN_MAX})")
            if avg > PLAIN_AVG:
                errors.append(f"In plain words averages {avg:.1f} words a sentence (at most {PLAIN_AVG})")
            if g > 12:
                errors.append(f"In plain words reads at grade {g} (at most 10; over 12 is an error)")
            elif g > 10:
                warnings.append(f"In plain words reads at grade {g} (aim for 10 or less)")
            if len(pids) < 2:
                errors.append(f"In plain words cites {len(pids)} claims (at least 2)")
            for k, p in enumerate(st["plain"]):
                everyone(p, "In plain words", PLAIN_SENT)
                evidence(p, "In plain words paragraph")
        # minute: Engineer layer, sparse code
        if not st["minute"] and not system:
            errors.append("no @minute summary")
        if st["minute"]:
            mw = sum(words(p) for p in st["minute"])
            mids = {x for p in st["minute"] for x in expand_ids(p)}
            mcode = sum(len(CODE_RE.findall(p)) for p in st["minute"])
            if mw > 120:
                errors.append(f"@minute is {mw} words (at most 120)")
            if len(mids) < 3:
                errors.append(f"@minute cites {len(mids)} claims (at least 3)")
            if mcode > MINUTE_CODE:
                errors.append(f"@minute uses {mcode} code spans (at most {MINUTE_CODE})")
            for p in st["minute"]:
                engineer(p, "minute paragraph")
                evidence(p, "minute paragraph")
        # words you'll see: the bridge from plain terms to code names
        for r in st["words_table"]:
            for part, what in ((r["term"], "Words you'll see term"), (r["means"], "Words you'll see meaning")):
                if CODE_RE.search(part) or identifiers(part):
                    errors.append(f"{what} must be plain words: {where(part)}")
            if len(r["means"].split()) > 30:
                errors.append(f"Words you'll see meaning over 30 words: {where(r['means'])}")
            if not r["names"]:
                errors.append(f"Words you'll see row '{r['term']}' names no code (put the code names in backticks)")
            if not r["ids"]:
                errors.append(f"Words you'll see row '{r['term']}' cites no claim")
            miss = self.unsupported(r["code"] + " " + r["means"], [x for x in r["ids"] if x in self.claims])
            if miss:
                errors.append(f"Words you'll see row '{r['term']}' states {', '.join(miss[:3])} found in neither its claims nor their code")
            cited.update(r["ids"])
        # at a glance: Engineer layer
        conditional = sum(bool(CONDITIONAL.match(c["text"])) for c in mod_claims)
        g_ = st["glance"]
        if g_ is None and conditional >= 5 and not system:
            errors.append(f"no At a glance table, and the module has {conditional} conditional claims")
        if g_ is not None:
            if not 3 <= len(g_["rows"]) <= 14:
                (errors if len(g_["rows"]) < 3 else warnings).append(f"At a glance has {len(g_['rows'])} rows (3 to 14)")
            for r in g_["rows"]:
                if not r["ids"]:
                    errors.append(f"at-a-glance row cites no claim: {where(r['when'])}")
                engineer(r["when"] + ". " + r["then"], "at-a-glance row")
                miss = self.unsupported(r["when"] + " " + r["then"], [x for x in r["ids"] if x in self.claims])
                if miss:
                    errors.append(f"at-a-glance row states {', '.join(miss[:3])} found in neither its claims nor their code: {where(r['when'])}")
                cited.update(r["ids"])
        # sections
        lo, hi = (2, 8) if system else (3, 6)
        if not lo <= len(st["sections"]) <= hi:
            (errors if len(st["sections"]) < lo - 1 else warnings).append(f"{len(st['sections'])} story sections ({lo} to {hi})")
        paths_seen = set()
        for sec in st["sections"]:
            everyone(sec["title"], "section heading")
            if len(sec["title"].split()) > 14:
                errors.append(f"section heading over 14 words: {where(sec['title'])}")
            if len(sec["title"].split()) < 4 or not VERB_HINT.search(sec["title"]):
                warnings.append(f"heading reads as a label, not an assertion: {sec['title']}")
            # every section opens with a plain lead (Everyone layer): readers who chose Everyone see the
            # heading, this lead and the figure, so no section is a bare heading for them
            lead = sec["blocks"][0] if sec["blocks"] else None
            if not lead or lead["t"] != "p":
                errors.append(f"section '{where(sec['title'])}' must open with a plain lead paragraph (no code, at most 60 words)")
            else:
                lead["lead"] = True
                everyone(lead["md"], f"lead of '{where(sec['title'])}'")
                if words(lead["md"]) > 60:
                    errors.append(f"lead of '{where(sec['title'])}' is {words(lead['md'])} words (at most 60)")
            figs = [b for b in sec["blocks"] if b["t"] == "fig"]
            if len(figs) > 1:
                errors.append(f"section '{where(sec['title'])}' has {len(figs)} figures (at most 1)")
            for b in sec["blocks"]:
                if b["t"] == "p" and b.get("lead"):
                    evidence(b["md"], "lead paragraph")
                elif b["t"] == "p":
                    engineer(b["md"], "paragraph")
                    evidence(b["md"], "paragraph")
                elif b["t"] == "ul":
                    for it in b["items"]:
                        engineer(it, "bullet")
                        evidence(it, "bullet")
                elif b["t"] == "fig":
                    self.check_figure(b, errors, warnings, cited, everyone)
                elif b["t"] == "path":
                    paths_seen.add(b["flow"])
                    n = self.flows.get(b["flow"])
                    if n is None:
                        errors.append(f"@path {b['flow']} is not a main path of the overview (known: {', '.join(sorted(self.flows))})")
                    elif [s_["n"] for s_ in b["steps"]] != list(range(1, n + 1)):
                        errors.append(f"@path {b['flow']} has steps {[s_['n'] for s_ in b['steps']]}; the path has {n}, numbered 1 to {n}")
                    for s_ in b["steps"]:
                        everyone(s_["md"], f"path {b['flow']} step {s_['n']}")
                        evidence(s_["md"], f"path {b['flow']} step {s_['n']}")
        if system:
            for f in sorted(set(self.flows) - paths_seen):
                errors.append(f"the system story has no @path for main path {f}")
        # watch out: Everyone layer
        if not st["watch"]:
            errors.append("no Watch out bullets")
        for it in st["watch"]:
            everyone(it, "watch-out bullet")
            evidence(it, "watch-out bullet")
        # acronyms in the Everyone layer: expanded there at first use, or universal
        alltext = " ".join(everyone_text)
        for acr in sorted({m.group(1) for t in everyone_text for m in ACRONYM.finditer(strip_chips(t))} - UNIVERSAL):
            if not re.search(rf"\({acr}s?\)|\b{acr}s?\s*\(", alltext) and acr.lower() not in defined_terms:
                errors.append(f"acronym {acr} is never spelled out in the Everyone layer (write it out once: words ({acr}))")
        # programming words in the Everyone layer need a plain row in Words you'll see (L78)
        etext = strip_chips(alltext).lower()
        for j in JARGON:
            if re.search(rf"\b{j}s?\b", etext) and not any(re.search(rf"\b{j}", term) for term in defined_terms):
                errors.append(f"the Everyone layer uses '{j}' with no row in Words you'll see; define it there in plain words, or say it plainly")
        # every term Words you'll see defines is used somewhere else in the story (coherence: no unused terms)
        body = " ".join([st["headline"], *st["plain"], *st["minute"], *st["watch"],
                         *[r["when"] + " " + r["then"] for r in (st["glance"] or {}).get("rows", [])]]
                        + [sec["title"] for sec in st["sections"]]
                        + [b["md"] for sec in st["sections"] for b in sec["blocks"] if b["t"] == "p"]
                        + [x for sec in st["sections"] for b in sec["blocks"] if b["t"] == "ul" for x in b["items"]]
                        + [x["md"] for sec in st["sections"] for b in sec["blocks"] if b["t"] == "path" for x in b["steps"]]
                        + [" ".join([b["title"], *(n["label"] for n in b["nodes"] + b["actors"] + b["lanes"]),
                                     *(e["label"] for e in b["edges"]), *(e["label"] + " " + e["state"] for e in b["events"]),
                                     *(x["title"] + " " + x["md"] for x in b["steps"])])
                           for sec in st["sections"] for b in sec["blocks"] if b["t"] == "fig"]).lower()
        for r in st["words_table"]:  # used by its plain term or by one of its code names
            used = lambda w: re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", body)
            if not used(r["term"]) and not any(used(n) for n in r["names"]):
                errors.append(f"Words you'll see defines '{r['term']}' but the story never uses it (cut the row or use the term)")
        # whole-story measures
        if eng_words:
            dens = 100 * eng_code / eng_words
            if dens > CODE_PER_100_ERR:
                errors.append(f"{dens:.1f} code spans per 100 words in the Engineer layer (at most {CODE_PER_100}; over {CODE_PER_100_ERR} is an error)")
            elif dens > CODE_PER_100:
                warnings.append(f"{dens:.1f} code spans per 100 words in the Engineer layer (aim for at most {CODE_PER_100})")
        if sent_lengths and sum(sent_lengths) / len(sent_lengths) > ENG_AVG:
            errors.append(f"Engineer-layer sentences average {sum(sent_lengths) / len(sent_lengths):.1f} words (at most {ENG_AVG})")
        if total_sent and passive / total_sent > 0.15:
            warnings.append(f"{passive}/{total_sent} sentences are passive (aim for at most 15%)")
        for x in sorted(cited):
            if x not in self.claims:
                errors.append(f"cites unknown claim {x}")
        defects = [c["id"] for c in mod_claims if c["section"].lower().startswith("suspected defect")]
        if defects and not set(defects) & cited:
            warnings.append(f"cites none of the module's {len(defects)} suspected defects")
        if not 700 <= st["words"] <= 1800 + (1200 if system else 0):
            warnings.append(f"story is {st['words']} words (700 to {1800 + (1200 if system else 0):,})")
        subs = {(c["section"], c["subsection"]) for c in mod_claims if c["subsection"]}
        hit = {(self.claims[x]["section"], self.claims[x]["subsection"]) for x in cited if x in self.claims and self.module_of[x] == module}
        coverage = len(subs & hit) / len(subs) if subs else 1.0
        if coverage < 0.5 and not system:
            warnings.append(f"chips reach {coverage:.0%} of the module's subsections")
        stats = {"words": st["words"], "claims_cited": len(cited), "coverage": round(coverage, 3),
                 "figures": sum(b["t"] == "fig" for s_ in st["sections"] for b in s_["blocks"]),
                 "plain_words": sum(words(p) for p in st["plain"]), "plain_grade": grade(" ".join(st["plain"])) if st["plain"] else None,
                 "code_per_100": round(100 * eng_code / eng_words, 2) if eng_words else 0.0,
                 "eng_avg_sentence": round(sum(sent_lengths) / len(sent_lengths), 1) if sent_lengths else 0.0,
                 "passive": round(passive / total_sent, 3) if total_sent else 0.0, "terms": len(st["words_table"])}
        return {"module": module, "errors": errors, "warnings": warnings, "story": st, "stats": stats}

    def check_figure(self, f: dict, errors: list, warnings: list, cited: set, everyone):
        name = f"figure {f['id']}"
        everyone(f["title"], f"{name} title")
        if f["kind"] == "timeline":
            lanes = {x["id"] for x in f["lanes"]}
            if not f["lanes"]:
                errors.append(f"{name}: a timeline needs lane rows")
            if not 2 <= len(f["events"]) <= 14:
                errors.append(f"{name}: {len(f['events'])} events (2 to 14)")
            if not f["title"].lower().startswith("example"):
                errors.append(f"{name}: a timeline is an example; its title starts with \"Example:\"")
            last = -1.0
            for ev in f["events"]:
                if ev["lane"] not in lanes:
                    errors.append(f"{name}: event at {ev['time']} names an undeclared lane {ev['lane']}")
                if ev["t"] < last:
                    errors.append(f"{name}: events go back in time at {ev['time']}")
                last = ev["t"]
                if not ev["ids"]:
                    errors.append(f"{name}: event at {ev['time']} cites no claim")
                for part in (ev["label"], ev["state"]):
                    everyone(part, f"{name} event at {ev['time']}")
                    if len(part.split()) > 6:
                        errors.append(f"{name}: event text over 6 words: {part}")
                # the time column is the example's own clock; values in the label and state must be cited
                miss = self.unsupported(ev["label"] + " " + ev["state"], ev["ids"])
                if miss:
                    errors.append(f"{name}: event at {ev['time']} states {', '.join(miss[:3])} found in neither its claims nor their code")
                cited.update(ev["ids"])
            for x in f["lanes"]:
                everyone(x["label"], f"{name} lane")
            return
        elems = f["nodes"] if f["kind"] != "sequence" else f["actors"]
        ids = {e["id"] for e in elems}
        if f["kind"] == "sequence" and not f["actors"]:
            errors.append(f"{name}: a sequence needs actor rows")
        if len(elems) > MAX_NODES:
            errors.append(f"{name}: {len(elems)} nodes (at most {MAX_NODES}; split it into an overview and a detail)")
        if not f["edges"]:
            errors.append(f"{name}: no edges or messages")
        for n in elems:
            everyone(n["label"], f"{name} label")
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
            everyone(e["label"], f"{name} edge label")
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
            everyone(s["title"], f"{name} step title")
            everyone(s["md"], f"{name} step '{s['title']}'")
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
        for e in r["errors"][:80]:
            eprint(f"ERROR: {f.stem}: {e}")
        s = r["stats"]
        eprint(f"{f.stem}: {len(r['errors'])} errors, {len(r['warnings'])} warnings; {s['words']} words "
               f"(plain {s['plain_words']}, grade {s['plain_grade']}), {s['code_per_100']} code spans per 100 words, "
               f"{s['claims_cited']} claims cited, {s['figures']} figures, {s['terms']} terms, coverage {s['coverage']:.0%}")
        bad += bool(r["errors"])
    if not files:
        eprint("no stories under _meta/story/")
    return 1 if bad or (a.module and len(files) < len(a.module)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
