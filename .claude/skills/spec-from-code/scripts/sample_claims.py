#!/usr/bin/env python3
"""Deterministic, stratified sample of claims for spot checks and falsification audits.

A grader who picks its own claims picks easy ones. This picks for it: per module, N claims with a
fixed seed, weighted toward {confirmed} (the claims a reader will trust) and toward claims in
normative sections (Behaviors, Validation rules, Error handling, ...), never from Open questions.

Usage: sample_claims.py <specs_dir> [--per-module 12] [--seed 7] [--module ID ...] [--out FILE.jsonl]
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from _common import eprint, is_universal, parse_claims, parse_frontmatter

NORMATIVE = {"Behaviors", "Validation rules", "Error handling", "State and data", "External interactions",
             "Configuration", "Concurrency and ordering", "Public surface", "Entry points", "Error catalog",
             "Settings", "Precedence", "Stores", "Schemas", "Invariants", "Global invariants", "System map"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--per-module", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--out", default=None)
    ap.add_argument("--universal-only", action="store_true",
                    help="sample only universal claims (always/never/unless/only...): the Phase 5 falsification pass")
    ap.add_argument("--universal-share", type=float, default=0.67,
                    help="share of confirmed picks drawn from universal claims when both kinds exist")
    a = ap.parse_args()
    specs = Path(a.specs).resolve()
    files = sorted(specs.glob("modules/*.md")) + sorted(specs.glob("0*.md"))
    out = []
    for fp in files:
        fm, body = parse_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
        mid = fm.get("module") or fm.get("kind")
        if a.module and mid not in a.module:
            continue
        claims = [c for c in parse_claims(body) if c["section"] != "Open questions and gaps"]
        rng = random.Random(f"{a.seed}:{mid}")
        if a.universal_only:
            claims = [c for c in claims if is_universal(c["text"])]
        conf = [c for c in claims if c["confidence"] == "confirmed"]
        inf = [c for c in claims if c["confidence"] == "inferred"]
        n_inf = 0 if a.universal_only else (min(len(inf), max(1, a.per_module // 4)) if inf else 0)
        n_conf = min(len(conf), a.per_module - n_inf)
        conf.sort(key=lambda c: (c["section"] not in NORMATIVE, rng.random()))
        uni = [c for c in conf if is_universal(c["text"])]
        rest = [c for c in conf if not is_universal(c["text"])]
        k_uni = min(len(uni), round(n_conf * (1.0 if a.universal_only else a.universal_share)))
        pick = uni[:k_uni] + rest[: n_conf - k_uni] + rng.sample(inf, n_inf)
        for c in pick:
            out.append({"module": mid, "file": str(fp.relative_to(specs)), **c})
    text = "".join(json.dumps(r) + "\n" for r in out)
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text, end="")
    eprint(f"sampled {len(out)} claims from {len(files)} spec files (seed {a.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
