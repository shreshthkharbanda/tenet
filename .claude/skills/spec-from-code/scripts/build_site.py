#!/usr/bin/env python3
"""Build the reader site for a spec tree: compile the data (site_data.py) and write index.html with the
reader's CSS and JS inlined (assets/site/), ready to open over HTTP or publish as a multi-file page.

  build_site.py <specs> --out DIR [--repo ROOT] [--eval EVAL] [--standalone]

--standalone wraps the page in its own <!doctype html> document; without it the page is a fragment for
hosts that supply the document shell (the Artifact publisher does). Prints the files to publish.
"""
from __future__ import annotations

import argparse
import html
import subprocess
import sys
from pathlib import Path

from _common import eprint, read_json

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets" / "site"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("specs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--eval", default=None)
    ap.add_argument("--standalone", action="store_true")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    cmd = [sys.executable, str(HERE / "site_data.py"), a.specs, "--out", str(out)]
    cmd += ["--repo", a.repo] if a.repo else []
    cmd += ["--eval", a.eval] if a.eval else []
    if subprocess.run(cmd).returncode:
        return 1
    book = read_json(out / "data" / "book.json")
    title = (book.get("title") or "Specification").removesuffix(": overview").removesuffix(" overview").strip() or "Specification"
    page = (ASSETS / "index.html").read_text(encoding="utf-8")
    page = page.replace("{{TITLE}}", html.escape(title if title.lower().endswith(" spec") else title + " Spec")).replace("{{CSS}}", (ASSETS / "app.css").read_text(encoding="utf-8"))
    page = page.replace("{{JS}}", (ASSETS / "app.js").read_text(encoding="utf-8").replace("</script", "<\\/script"))
    if a.standalone:
        page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n</head>\n<body>\n'
                + page + "\n</body>\n</html>\n")
    (out / "index.html").write_text(page, encoding="utf-8")
    files = sorted(p.relative_to(out).as_posix() for p in (out / "data").glob("*.json"))
    eprint(f"site: {out / 'index.html'} ({len(page) / 1e3:.0f} KB) + {len(files)} data files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
