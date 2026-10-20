#!/usr/bin/env python3
"""Compile a spec tree into the data a reader site renders: one book index plus, per spec file, its
section tree, prose, tables and claims, and the source lines each claim cites. Deterministic: the site
never states anything the spec files do not (the narrative layer is separate, see check_story.py).

  site_data.py <specs> --out DIR [--repo ROOT] [--eval EVAL] [--max-lines 40]

Writes DIR/data/book.json, DIR/data/f-<slug>.json (blocks and claims of one spec file) and
DIR/data/s-<slug>.json (source snippets keyed by ref). Inline markdown is rendered to escaped HTML
here, so the page never parses markdown or injects spec text unescaped.
"""
from __future__ import annotations

import argparse
import html
import re
import subprocess
from pathlib import Path

from _common import (CLAIM_RE, XREF_RE, eprint, parse_frontmatter, read_json, ref_path, ref_span, repo_lines, split_refs,
                     write_json)

CODE = re.compile(r"`([^`\n]+)`")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITAL = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
RANGE = re.compile(r"\[([A-Z][A-Z0-9]{1,11}-\d{3,4})\]-\[([A-Z][A-Z0-9]{1,11}-\d{3,4})\]")
TABLE_SEP = re.compile(r"^\|[\s:|-]+\|?$")
NUM_ITEM = re.compile(r"^(\d+)\.\s+(.*)$")


def slug(rel: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", rel.lower().removesuffix(".md")).strip("-")


def inline(md: str) -> str:
    """Escaped HTML for one line of spec markdown: code spans, bold, italics, and claim references
    as links (ranges like [A-001]-[A-009] stay one link to the first, labelled as the range)."""
    out, last = [], 0
    for m in CODE.finditer(md):
        out.append(_prose(md[last:m.start()]))
        out.append(f"<code>{html.escape(m.group(1))}</code>")
        last = m.end()
    out.append(_prose(md[last:]))
    return "".join(out)


CHIP = r'<a class="xr" [^>]*>[^<]*</a>'
CHIP_RUN = re.compile(rf"{CHIP}(?:\s*(?:,|;|and|&ndash;|-)?\s*{CHIP})*")


def _prose(s: str) -> str:
    s = html.escape(s, quote=False)
    s = RANGE.sub(lambda m: f'<a class="xr" href="#{m.group(1)}" data-id="{m.group(1)}">{m.group(1)}&ndash;{m.group(2).split("-")[1]}</a>', s)
    s = XREF_RE.sub(lambda m: f'<a class="xr" href="#{m.group(1)}" data-id="{m.group(1)}">{m.group(1)}</a>', s)
    # a run of chips is one citation: the Everyone lens shows it as one quiet marker (L80)
    s = CHIP_RUN.sub(lambda m: f'<span class="cites">{m.group(0)}</span>', s)
    s = BOLD.sub(r"<strong>\1</strong>", s)
    return ITAL.sub(r"<em>\1</em>", s)


def plain(md: str) -> str:
    return re.sub(r"\s+", " ", md.replace("`", "").replace("**", "")).strip()


def cells(row: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", row.strip().strip("|"))]


def parse_file(text: str) -> tuple[dict, list[dict], dict]:
    """(frontmatter, sections, claims). A section is {id, title, level, blocks}; blocks are
    p / claim / ul / ol / table / code. Claims carry their section path."""
    fm, body = parse_frontmatter(text)
    sections: list[dict] = []
    claims: dict[str, dict] = {}
    cur = {"id": "top", "title": "", "level": 1, "blocks": []}
    sections.append(cur)
    h2 = ""
    lines = body.splitlines()
    i, para, in_comment = 0, [], False

    def flush():
        if para:
            cur["blocks"].append({"t": "p", "h": inline(" ".join(x.strip() for x in para))})
            para.clear()

    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if in_comment or st.startswith("<!--"):
            in_comment = "-->" not in st
            i += 1
            continue
        if ln.startswith("#"):
            flush()
            level = len(ln) - len(ln.lstrip("#"))
            title = ln.lstrip("#").strip()
            if level == 1:
                sections[0]["title"] = title
            else:
                h2 = title if level == 2 else h2
                cur = {"id": slug(title)[:60] or f"s{len(sections)}", "title": title, "th": inline(title),
                       "level": level, "parent": None if level == 2 else h2, "blocks": []}
                sections.append(cur)
            i += 1
            continue
        if st.startswith("```"):
            flush()
            lang, buf = st[3:].strip(), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            cur["blocks"].append({"t": "code", "lang": lang, "text": "\n".join(buf)})
            i += 1
            continue
        if st.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not TABLE_SEP.match(lines[i].strip()):
                    rows.append([inline(c) for c in cells(lines[i])])
                i += 1
            if rows:
                cur["blocks"].append({"t": "table", "head": rows[0], "rows": rows[1:]})
            continue
        m = CLAIM_RE.match(ln)
        if m:
            flush()
            refs, txt = split_refs(m.group("rest"))
            cid = m.group("id")
            claims[cid] = {"id": cid, "conf": m.group("conf"), "refs": refs, "h": inline(txt), "plain": plain(txt),
                           "xr": sorted(set(XREF_RE.findall(txt)) - {cid}), "sec": h2,
                           "sub": cur["title"] if cur["level"] >= 3 else ""}
            blk = cur["blocks"][-1] if cur["blocks"] else None
            if blk and blk["t"] == "claims":
                blk["ids"].append(cid)
            else:
                cur["blocks"].append({"t": "claims", "ids": [cid]})
            i += 1
            continue
        # an indented line right under a claim is that claim's detail, shown under it (L76)
        blk = cur["blocks"][-1] if cur["blocks"] else None
        if blk and blk["t"] == "claims" and ln.startswith(("  ", "\t")) and st and not para:
            claims[blk["ids"][-1]].setdefault("detail", []).append(inline(re.sub(r"^[-*]\s+", "", st)))
            claims[blk["ids"][-1]]["plain"] += " " + plain(re.sub(r"^[-*]\s+", "", st))
            i += 1
            continue
        lm = re.match(r"^\s*[-*]\s+(.*)$", ln)
        nm = NUM_ITEM.match(st)
        if lm or nm:
            flush()
            kind = "ol" if nm else "ul"
            item = (nm.group(2) if nm else lm.group(1)).strip()
            # continuation lines indented under the item
            while i + 1 < len(lines) and lines[i + 1].startswith("  ") and lines[i + 1].strip() \
                    and not re.match(r"^\s*([-*]|\d+\.)\s", lines[i + 1]):
                i += 1
                item += " " + lines[i].strip()
            blk = cur["blocks"][-1] if cur["blocks"] else None
            entry = {"h": inline(item), "x": sorted(set(XREF_RE.findall(item)))}
            if blk and blk["t"] == kind:
                blk["items"].append(entry)
            else:
                cur["blocks"].append({"t": kind, "items": [entry]})
            i += 1
            continue
        if not st:
            flush()
        else:
            para.append(ln)
        i += 1
    flush()
    return fm, [s for s in sections if s["blocks"] or s["level"] > 1 or s["title"]], claims


def render_story(st: dict, stats: dict | None = None) -> dict:
    """A checked story with its markdown rendered to escaped HTML (chips become claim links)."""
    def fig(f):
        return {"kind": f["kind"], "id": f["id"], "title": html.escape(f["title"]),
                "nodes": [{"id": n["id"], "label": n["label"], "ids": n["ids"]} for n in f["nodes"]],
                "actors": [{"id": a["id"], "label": a["label"]} for a in f["actors"]],
                "lanes": [{"id": x["id"], "label": x["label"]} for x in f.get("lanes", [])],
                "events": [{"time": e["time"], "t": e["t"], "lane": e["lane"], "label": e["label"], "state": e["state"],
                            "ids": e["ids"]} for e in f.get("events", [])],
                "edges": [{"a": e["a"], "b": e["b"], "label": e["label"], "ids": e["ids"]} for e in f["edges"]],
                "rows": [{"in": inline(r["in"]), "out": inline(r["out"]), "ids": r["ids"]} for r in f.get("rows", [])],
                "steps": [{"target": x["target"], "title": html.escape(x["title"]), "h": inline(x["md"]), "ids": x["ids"]} for x in f["steps"]]}

    from check_story import block_layer

    def block(b):
        return {"layer": block_layer(b), **body(b)}

    def body(b):
        if b["t"] == "p":
            return {"t": "p", "h": inline(b["md"]), "lead": bool(b.get("lead"))}
        if b["t"] == "ul":
            return {"t": "ul", "items": [{"h": inline(x)} for x in b["items"]]}
        if b["t"] == "path":
            return {"t": "path", "flow": b["flow"], "steps": [{"n": x["n"], "h": inline(x["md"])} for x in b["steps"]]}
        return {"t": "fig", **fig(b)}
    return {
        "headline": inline(st["headline"]), "plain": [inline(p) for p in st.get("plain", [])],
        "minute": [inline(p) for p in st["minute"]],
        "words": [{"term": inline(r["term"]), "means": inline(r["means"]), "code": inline(r["code"]), "ids": r["ids"]}
                  for r in st.get("words_table", [])],
        "glance": [{"when": inline(r["when"]), "then": inline(r["then"]), "ids": r["ids"]} for r in (st["glance"] or {}).get("rows", [])],
        "sections": [{"title": inline(sec["title"]), "plain": plain(sec["title"]), "blocks": [block(b) for b in sec["blocks"]]}
                     for sec in st["sections"]],
        "watch": [inline(x) for x in st["watch"]], "words_n": st["words"],
        "everyone_words": (stats or {}).get("everyone_words"), "all_words": (stats or {}).get("all_words"),
    }


def flows(sections: list[dict]) -> list[dict]:
    """The overview's numbered 'Main paths' become step-by-step walkthroughs."""
    out = []
    for s in sections:
        if s["level"] == 3 and (s.get("parent") or "").lower().startswith("main path"):
            steps = [it for b in s["blocks"] if b["t"] == "ol" for it in b["items"]]
            if steps:
                title = re.sub(r"^\d+\.\s*", "", s["title"])
                sl = slug(title)
                sl = sl if len(sl) <= 48 else sl[:48].rsplit("-", 1)[0]  # cut at a word boundary
                out.append({"id": "flow-" + sl, "title": title, "steps": [{"h": it["h"], "x": it["x"]} for it in steps]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--eval", default=None, help="eval dir, for held-out fidelity (default: _meta/run.json eval_dir)")
    ap.add_argument("--max-lines", type=int, default=40, help="source lines kept per ref; longer spans are cut")
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    meta = specs / "_meta"
    run = read_json(meta / "run.json") if (meta / "run.json").exists() else {}
    repo = Path(a.repo or run.get("repo") or ".").resolve()
    ev = Path(a.eval or run.get("eval_dir") or "")
    out = Path(a.out).resolve() / "data"
    out.mkdir(parents=True, exist_ok=True)

    remote = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    web = re.sub(r"\.git$", "", re.sub(r"^git@([^:]+):", r"https://\1/", remote)) if remote else ""
    validation = read_json(ev / "validation.json").get("modules", {}) if ev and (ev / "validation.json").exists() else {}
    evidence = read_json(meta / "evidence-report.json").get("modules", {}) if (meta / "evidence-report.json").exists() else {}
    ev_state = {}
    for mid, r in evidence.items():
        for kind in ("passed", "flaky", "hollow", "failed", "stale"):
            for cid in r.get(kind, []):
                ev_state[cid] = "flaky" if kind == "flaky" else kind  # flaky ids also sit in passed; later kinds win
    mods = {m["id"]: m for m in read_json(meta / "modules.json")["modules"]} if (meta / "modules.json").exists() else {}

    files = sorted(specs.glob("0*.md")) + sorted(specs.glob("modules/*.md"))
    # chapter stories (references/story.md): shown only when G8 passes, so the site never shows an
    # unchecked story; a failing one is reported and left out
    from check_story import Checker
    story_ck = Checker(specs, repo) if (meta / "story").exists() else None
    book = {"title": "", "repo": web, "commit": "", "files": [], "flows": [], "glossary": [], "defects": [], "owner": {}}
    total_snips = 0
    for fp in files:
        rel = fp.relative_to(specs).as_posix()
        fm, sections, claims = parse_file(fp.read_text(encoding="utf-8", errors="replace"))
        sl = slug(rel)
        book["commit"] = book["commit"] or str(fm.get("commit") or "")
        mid = fm.get("module")
        snippets = {}
        for c in claims.values():
            c["ev"] = ev_state.get(c["id"])
            c["defect"] = c["sec"].lower().startswith("suspected defect")
            book["owner"][c["id"]] = sl
            for r in c["refs"]:
                if r in snippets:
                    continue
                sp = ref_span(repo, r)
                p = ref_path(r)
                if not sp:
                    snippets[r] = {"p": p}
                    continue
                path, lo, hi = sp
                if "::" not in r and ":" not in r.replace(p, "", 1):
                    snippets[r] = {"p": path}  # a bare file ref: link only
                    continue
                src = repo_lines(repo, path)
                keep = src[lo - 1:min(hi, lo - 1 + a.max_lines)]
                snippets[r] = {"p": path, "a": lo, "b": hi, "l": keep}
                total_snips += 1
        for c in claims.values():
            if c["defect"]:
                book["defects"].append({"id": c["id"], "file": sl, "h": c["h"], "conf": c["conf"]})
        title = sections[0]["title"] if sections else rel
        v = validation.get(mid, {}) if mid else {}
        counts = {k: sum(c["conf"] == k for c in claims.values()) for k in ("confirmed", "inferred", "gap")}
        purpose = next((s for s in sections if s["title"].lower() == "purpose"), None)
        lede = next((b["h"] for b in (purpose or {}).get("blocks", []) if b["t"] == "p"), "")
        book["files"].append({
            "slug": sl, "rel": rel, "kind": fm.get("kind"), "module": mid, "prefix": fm.get("prefix"), "title": title,
            "lede": lede, "claims": counts, "defects": sum(c["defect"] for c in claims.values()),
            "status": v.get("status") or fm.get("status"), "holdout": v.get("holdout_fidelity"), "holdout_n": v.get("holdout_n"),
            "holdout_low": v.get("holdout_wilson_lower"), "control": v.get("control_fidelity"),
            "evidence": evidence.get(mid, {}).get("evidence_rate") if mid else None,
            "scope": fm.get("scope") or (mods.get(mid, {}).get("files") if mid else None),
            "sections": [{"id": s["id"], "title": s["title"], "level": s["level"]} for s in sections[1:]],
            "words": len(re.sub(r"<[^>]+>", " ", " ".join(b.get("h", "") for s in sections for b in s["blocks"])
                                + " ".join(c["plain"] for c in claims.values())).split()),
        })
        if fm.get("kind") == "overview":
            book["title"] = title
            book["flows"] = flows(sections)
            for s in sections:
                if s["title"].lower() == "glossary":
                    for b in s["blocks"]:
                        for it in b.get("items", []):
                            m = re.match(r"<strong>(.+?)</strong>:?\s*(.*)$", it["h"])
                            if m:
                                book["glossary"].append({"term": m.group(1), "h": m.group(2), "x": it["x"]})
        story = None
        sf = meta / "story" / f"{mid}.md"
        if mid and story_ck and sf.exists():
            r = story_ck.check(mid, sf.read_text(encoding="utf-8", errors="replace"))
            write_json(meta / "story" / f"{mid}.check.json", {k: v for k, v in r.items() if k != "story"})
            if r["errors"]:
                eprint(f"WARN: {mid}: story left out, G8 has {len(r['errors'])} errors (first: {r['errors'][0]})")
                book["files"][-1]["story_errors"] = len(r["errors"])
            else:
                story = render_story(r["story"], r["stats"])
                book["files"][-1]["story"] = {"words": r["stats"]["words"], "everyone_words": r["stats"]["everyone_words"],
                                              "all_words": r["stats"]["all_words"], "figures": r["stats"]["figures"],
                                              "headline": inline(r["story"]["headline"]),
                                              "grade": r["stats"]["plain_grade"], "code_per_100": r["stats"]["code_per_100"]}
        write_json(out / f"f-{sl}.json", {"slug": sl, "rel": rel, "title": title, "sections": sections, "claims": claims,
                                          "story": story})
        write_json(out / f"s-{sl}.json", snippets)
    # the reference graph: how often each spec file's claims and prose point into another's claims. It lays
    # out the system map and names the participants of each flow step, mechanically, from the spec itself.
    links: dict[tuple[str, str], int] = {}
    for fp in files:
        src = slug(fp.relative_to(specs).as_posix())
        for x in XREF_RE.findall(fp.read_text(encoding="utf-8", errors="replace")):
            dst = book["owner"].get(x)
            if dst and dst != src:
                links[(src, dst)] = links.get((src, dst), 0) + 1
    book["links"] = [{"from": k[0], "to": k[1], "n": n} for k, n in sorted(links.items(), key=lambda kv: -kv[1])]
    for fl in book["flows"]:
        for st in fl["steps"]:
            st["who"] = sorted({book["owner"][x] for x in st["x"] if x in book["owner"]},
                               key=lambda s: -sum(book["owner"].get(x) == s for x in st["x"]))
    # reading order: the overview's "Reading order" list names spec files; the rest follow in file order
    order: list[str] = []
    ov = next((f for f in files if parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))[0].get("kind") == "overview"), None)
    if ov:
        _, osecs, _ = parse_file(ov.read_text(encoding="utf-8", errors="replace"))
        for s_ in osecs:
            if s_["title"].lower().startswith("reading order"):
                for b in s_["blocks"]:
                    for it in b.get("items", []):
                        for m in re.finditer(r"<code>([\w./-]+\.md)</code>", it["h"]):
                            sl = slug(m.group(1))
                            if any(f["slug"] == sl for f in book["files"]) and sl not in order:
                                order.append(sl)
        # defects the overview singles out lead the home page's worklist
        otext = ov.read_text(encoding="utf-8", errors="replace")
        dids = {d["id"] for d in book["defects"]}
        book["headline_defects"] = [x for x in dict.fromkeys(XREF_RE.findall(otext)) if x in dids]
    book["order"] = order + [f["slug"] for f in book["files"] if f["slug"] not in order]
    # the system story opens the book; its @path blocks give each walkthrough its plain-words steps
    sysf = meta / "story" / "_system.md"
    if story_ck and sysf.exists():
        r = story_ck.check("_system", sysf.read_text(encoding="utf-8", errors="replace"))
        write_json(meta / "story" / "_system.check.json", {k: v for k, v in r.items() if k != "story"})
        if r["errors"]:
            eprint(f"WARN: the system story is left out, G8 has {len(r['errors'])} errors (first: {r['errors'][0]})")
        else:
            book["system"] = render_story(r["story"], r["stats"])
            for sec in book["system"]["sections"]:
                for b in sec["blocks"]:
                    if b["t"] == "path":
                        for fl in book["flows"]:
                            if fl["id"] == b["flow"]:
                                for st_, ps in zip(fl["steps"], b["steps"]):
                                    st_["plain"] = ps["h"]
                                fl["section"] = sec["title"]
    book["stats"] = {"files": len(files), "claims": len(book["owner"]), "defects": len(book["defects"]), "snippets": total_snips}
    write_json(out / "book.json", book)
    size = sum(f.stat().st_size for f in out.glob("*.json"))
    eprint(f"site data: {len(files)} spec files, {len(book['owner'])} claims, {len(book['flows'])} flows, "
           f"{len(book['defects'])} suspected defects, {total_snips} source snippets, {size / 1e6:.1f} MB -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
