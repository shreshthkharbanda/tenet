#!/usr/bin/env python3
"""Candidate contradictions for the Reconciler: pairs of claims whose refs cite overlapping lines of
the same file, from different spec files OR the same one. Two descriptions of the same code are where
specs disagree; reading thousands of claims for contradictions is hopeless, checking a few hundred
pairs is not. Pairs whose texts share a distinctive literal with different values nearby are ranked
first.

Same-file pairs matter: a reviser who adds a corrected claim without deleting the old one leaves two
claims on the same lines that disagree (red team E5). Wide refs (over --max-span lines) pair only when
the two claims also share a backticked identifier, so widening a ref no longer hides a claim from the
worklist (red team E4b) without pairing everything that cites a big function. Symbol refs resolve to
the definition's lines when the repo is known.

The head of the worklist is filled by rank, alternating between cross-file and same-file pairs so
neither kind starves the other.

Usage: find_overlaps.py <specs_dir> [--repo ROOT] [--max 400] -> _meta/overlaps.jsonl
"""
from __future__ import annotations

import argparse
import random
import re
from pathlib import Path

from _common import LINE_REF_RE, XREF_RE, eprint, parse_claims, parse_frontmatter, read_json, ref_span, write_jsonl

NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
LIT = re.compile(r"`([^`]{2,60})`")
IDENT = re.compile(r"`([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)(?:\([^`]*\))?`")
COMMON_IDENTS = {"None", "True", "False", "null", "self", "cls", "model", "kwargs", "args", "str", "int", "dict", "list",
                 "bool", "float", "data", "value", "name", "type", "result", "response", "request", "error", "default"}


def jaccard(x: str, y: str) -> float:
    a, b = set(w.lower() for w in WORD.findall(x)), set(w.lower() for w in WORD.findall(y))
    return len(a & b) / len(a | b) if a | b else 0.0


def spans(refs: list[str], repo: Path | None) -> list[tuple[str, int, int]]:
    out = []
    for r in refs:
        if repo is not None:
            sp = ref_span(repo, r)
            if sp:
                out.append(sp)
            continue
        m = LINE_REF_RE.match(r.strip())
        if m and "::" not in r:
            a = int(m.group(2))
            out.append((m.group(1), a, int(m.group(3) or a)))
    return out


def subject(c: dict) -> set[str]:
    """What a claim is about, for pairing wide refs: its distinctive backticked identifiers and literals
    (`within_baseline_budget`, `32768`), its own ID, and the claim IDs it points to. Two claims that
    share one of these, or where one points at the other, describe the same thing."""
    text = c["text"]
    out = {"#" + c["id"]} | {"#" + x for x in XREF_RE.findall(text)}
    for t in IDENT.findall(text):
        last = t.split(".")[-1]
        if len(last) >= 4 and last not in COMMON_IDENTS:
            out |= {t, last}
    for t in LIT.findall(text):
        t = t.strip()
        if len(t) >= 3 and t not in COMMON_IDENTS and not IDENT.fullmatch("`" + t + "`"):
            out.add(t)
    return out


def related(si: set[str], sj: set[str], idi: str, idj: str) -> bool:
    """Shared subject tokens other than each claim's own ID, or one claim pointing at the other."""
    return bool((si - {"#" + idi}) & (sj - {"#" + idj})) or "#" + idj in si or "#" + idi in sj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--repo", default=None, help="repo root (default: _meta/inventory.json summary.repo_root)")
    ap.add_argument("--max", type=int, default=400)
    ap.add_argument("--max-span", type=int, default=120,
                    help="refs wider than this many lines pair only with claims sharing a backticked identifier")
    ap.add_argument("--tail-sample", type=int, default=60,
                    help="append this many random pairs from below the cut, marked tail_sample, so the yield of the "
                         "unjudged tail is measured instead of assumed")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    repo = Path(a.repo).resolve() if a.repo else None
    if repo is None and (specs / "_meta" / "inventory.json").exists():
        root = read_json(specs / "_meta" / "inventory.json").get("summary", {}).get("repo_root")
        repo = Path(root) if root and Path(root).is_dir() else None
    claims = []  # (file, claim, spans, subject tokens)
    for fp in sorted(specs.glob("modules/*.md")) + sorted(specs.glob("0*.md")):
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        for c in parse_claims(body):
            sp = spans(c["refs"], repo)
            if sp:
                claims.append((fp.relative_to(specs).as_posix(), c, sp, subject(c)))
    by_path: dict[str, list[int]] = {}
    for i, (_, _, sp, _) in enumerate(claims):
        for p, _, _ in sp:
            by_path.setdefault(p, []).append(i)
    pairs, seen = [], set()
    for p, idx in by_path.items():
        idx = sorted(set(idx))
        for x in range(len(idx)):
            for y in range(x + 1, len(idx)):
                i, j = idx[x], idx[y]
                if (i, j) in seen:
                    continue
                si = [s for s in claims[i][2] if s[0] == p]
                sj = [s for s in claims[j][2] if s[0] == p]
                narrow = wide = False
                for _, a1, b1 in si:
                    for _, a2, b2 in sj:
                        if not (b1 < a2 or b2 < a1):
                            if b1 - a1 <= a.max_span and b2 - a2 <= a.max_span:
                                narrow = True
                            else:
                                wide = True
                if not narrow and not (wide and related(claims[i][3], claims[j][3], claims[i][1]["id"], claims[j][1]["id"])):
                    continue
                seen.add((i, j))
                ti, tj = claims[i][1]["text"], claims[j][1]["text"]
                ni, nj = set(NUM.findall(ti)), set(NUM.findall(tj))
                li, lj = set(LIT.findall(ti)), set(LIT.findall(tj))
                # suspicion: shared literals (same subject) with differing numbers or literals (different value)
                score = len(li & lj) * 2 + (3 if (ni and nj and ni != nj) else 0) + (2 if (li ^ lj) and (li & lj) else 0)
                sim = jaccard(ti, tj)
                kind = "duplicate" if sim >= 0.45 else "same-code"
                pairs.append({"score": score, "similarity": round(sim, 3), "kind": kind, "path": p,
                              "same_file": claims[i][0] == claims[j][0], "via": "lines" if narrow else "wide-ref+identifier",
                              "a": {"file": claims[i][0], "id": claims[i][1]["id"], "refs": claims[i][1]["refs"], "text": ti},
                              "b": {"file": claims[j][0], "id": claims[j][1]["id"], "refs": claims[j][1]["refs"], "text": tj}})
    # duplicates whose values differ are the likeliest real contradictions; then other suspicious pairs
    pairs.sort(key=lambda r: (-(r["kind"] == "duplicate" and r["score"] >= 3), -r["score"], -r["similarity"]))
    # Fill the head from both kinds in proportion to their suspicious pairs (score >= 3), each in rank
    # order, so a flood of same-file pairs cannot push cross-file contradictions out, nor the reverse.
    cross = [r for r in pairs if not r["same_file"]]
    same = [r for r in pairs if r["same_file"]]
    wc = max(1, sum(r["score"] >= 3 for r in cross)) if cross else 0
    ws = max(1, sum(r["score"] >= 3 for r in same)) if same else 0
    ranked, ci, si = [], 0, 0
    while ci < len(cross) or si < len(same):
        take_cross = si >= len(same) or (ci < len(cross) and ci * ws <= si * wc)
        if take_cross:
            ranked.append(cross[ci])
            ci += 1
        else:
            ranked.append(same[si])
            si += 1
    head, tail = ranked[: a.max], ranked[a.max:]
    sample = random.Random(a.seed).sample(tail, min(a.tail_sample, len(tail)))
    for r in sample:
        r["tail_sample"] = True
    write_jsonl(specs / "_meta" / "overlaps.jsonl", head + sample)
    dups = [r for r in pairs if r["kind"] == "duplicate"]
    dup_conflict = [r for r in dups if r["score"] >= 3]
    write_jsonl(specs / "_meta" / "overlaps-meta.jsonl", [{"total_pairs": len(pairs), "cross_file": len(cross),
                                                          "same_file": len(same),
                                                          "via_wide_ref": sum(r["via"] != "lines" for r in pairs),
                                                          "judged_head": len(head), "tail": len(tail),
                                                          "tail_sampled": len(sample)}])
    files_dup: dict[str, int] = {}
    for r in dups:
        for side in ("a", "b"):
            files_dup[r[side]["file"]] = files_dup.get(r[side]["file"], 0) + 1
    eprint(f"overlaps: {len(pairs)} pairs on shared lines ({len(cross)} cross-file, {len(same)} same-file, "
           f"{sum(r['via'] != 'lines' for r in pairs)} via a wide ref and a shared identifier); {len(dups)} near-duplicates "
           f"({len(dup_conflict)} with differing values); top {min(len(pairs), a.max)} -> _meta/overlaps.jsonl"
           + ("" if repo else "; symbol refs skipped (no repo: pass --repo)"))
    eprint("near-duplicate involvement by file: " + ", ".join(f"{k} {v}" for k, v in sorted(files_dup.items(), key=lambda kv: -kv[1])[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
