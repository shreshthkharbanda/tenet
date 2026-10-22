# LiteLLM router spec: where this run stopped

This is the output of running the `spec-from-code` skill on LiteLLM's router (commit
`93b79d2587d186fb7266556a34a22d03f187a3da`), kept so the work survives the session that made it. It holds the
specs (`modules/`, `00-overview.md` to `03-config.md`, `INDEX.md`), the plain-language stories
(`_meta/story/`), the last story audit rows (`_meta/audit/`), and the queue of claim problems the audit
found (`_meta/revise/story-claim-notes.jsonl`). It leaves out evidence caches, rendered briefs, per-worker
reports and the held-out probe answers.

Reader site (private, owned by the session's user): https://claude.ai/artifact/HTh2Ud44s3qTwvm9NeeAvZ, version 2.

## Scope

The router only: `litellm/router.py` and `litellm/router_utils/`, about 26k of the package's 976k lines
(3%). Provider translation (`litellm/llms`, 243k lines), the proxy (408k), the SDK core (`main.py`,
`utils.py`, `litellm_core_utils`, caching, cost) and the integrations (69k) are not covered.

## State at the stop

| Part | State |
| --- | --- |
| 10 module stories | Every unit judged supported by the last recheck: 1,454 of 1,454 sentences, glossary rows, At-a-glance rows, figure steps, timeline rows and Watch-out bullets. G8 passes with 0 errors. Four stories exceed the 1,800-word prose limit (1,814 to 1,891), kept because putting back a claim's condition costs words. Router-selection's plain-language layer runs about 2,950 words against the 2,400-word (10-minute) target. |
| System story (`_system.md`) | Last full judge: 182 of 207 units supported, 20 overstated and 5 distorted (`_meta/audit/_system.jsonl`). A fixer for those 25 rows was started and stopped by the org spend limit before reporting; `_system.md` still passes G8 and the site shows it with those 25 units unrepaired. |
| Comprehension | Not re-measured after the last repairs. Latest readings, all taken on earlier versions: failure-handling reader answers 9 of 25 held-out questions fully, 2 contradicted (round 1: 8 and 3); teach-back 20 correct, 1 vague, 0 wrong. Router-selection: 1 contradicted answer, 3 wrong teach-back statements (since repaired). |
| Claim problems | 58 notes in `_meta/revise/story-claim-notes.jsonl`: claims the audit found wrong, looser than their code, or missing a case. Feed them to the reviser; the stories follow the claims as written. |

## To resume

1. `render_briefs.py --role story-fixer --module _system --round 3 ...` (the brief reads the rows in
   `_meta/audit/_system.jsonl`), then `--role story-recheck`.
2. Re-measure comprehension on the ten stories: `story_probe.py snapshot`, story-reader, story-scorer,
   persona-reader, teachback-judge (references/audit.md). Narrator rewrite only for what a reader got
   wrong; story-fixer and story-recheck for faithfulness (references/learnings.md, L84, L87).
3. Revise the 58 claims, then re-run the claim gates (G1 to G7) on the touched modules.
4. Rebuild the site: `build_site.py <specs> --out <dir> --repo <litellm checkout>`.

## Loose ends

- Two artifacts were published by workers by mistake and never deleted, pending the user's say-so:
  https://claude.ai/artifact/7swJkuVGKPmnqfkaGEiK38 and https://claude.ai/artifact/EhgNqfvkcT6K1bpcR5tEnL.
- The reader site's accuracy meter ("passed the accuracy check") comes from the ledger's held-out probes and
  has not been re-run for the revised claims.
