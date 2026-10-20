#!/usr/bin/env python3
"""Durable dispatch log, so orchestration survives a container restart.

A restart stops every running subagent and wipes the orchestrator's memory of what it launched; the
agents can be resumed from their transcripts (SendMessage to the agent id), but only if someone
recorded the ids. This log is that record, kept on disk next to the specs.

  dispatch.py add     --specs S --role R --module M [--round N] --brief PATH --agent ID
  dispatch.py done    --specs S --agent ID [--status ok|failed|lost]
  dispatch.py running --specs S            # entries launched but not done: resume these after a restart
  dispatch.py next    --specs S [--cap 18] # queued briefs that fit under the cap (queue.txt minus launched)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def load(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "done", "running", "next"])
    ap.add_argument("--specs", required=True)
    ap.add_argument("--role")
    ap.add_argument("--module")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--brief")
    ap.add_argument("--agent")
    ap.add_argument("--status", default="ok")
    ap.add_argument("--cap", type=int, default=18)
    a = ap.parse_args()
    meta = Path(a.specs).resolve() / "_meta"
    log = meta / "dispatch.jsonl"
    rows = load(log)
    if a.cmd == "add":
        rows.append({"role": a.role, "module": a.module, "round": a.round, "brief": a.brief, "agent": a.agent,
                     "status": "running", "launched": time.strftime("%Y-%m-%dT%H:%M:%S")})
    elif a.cmd == "done":
        hit = [r for r in rows if r["agent"] == a.agent and r["status"] == "running"]
        if not hit:
            raise SystemExit(f"no running entry for agent {a.agent}")
        for r in hit:
            r["status"] = a.status
            r["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    elif a.cmd == "running":
        for r in rows:
            if r["status"] == "running":
                print(f"{r['agent']}\t{r['role']}\t{r['module']}\tround {r['round']}\t{r['brief']}")
        return 0
    elif a.cmd == "next":
        launched = {r["brief"] for r in rows if r["status"] in ("running", "ok")}
        running = sum(1 for r in rows if r["status"] == "running")
        q = meta / "queue.txt"
        queued = [l.strip() for l in q.read_text().splitlines() if l.strip()] if q.exists() else []
        for b in [b for b in queued if b not in launched][: max(0, a.cap - running)]:
            print(b)
        return 0
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
