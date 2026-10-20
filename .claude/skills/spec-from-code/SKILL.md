---
name: spec-from-code
description: Recover a complete, validated, human-readable behavioral specification from an existing codebase by fanning out subagents (survey, per-module extraction, cross-cutting extraction, reconciliation, code-only probing, spec-only answering, judging, revision, optional rebuild) with mechanical gates at every step. Use this whenever the user wants to "spec out", "document the behavior of", "reverse-engineer", "decompile to English", "write the spec for", "generate specs from", "understand this whole repo", "make this codebase reviewable", or "turn code into a spec", for any repo or subsystem, even if they do not say "spec". Also use for "re-validate the specs", "update the specs after changes", or "how faithful are these specs". Not for writing a spec for code that does not exist yet (that is spec-first development, a different job).
---

# spec-from-code

Compile a codebase into a hierarchical natural-language specification, then prove the spec carries the
code's behavior. The output is a `specs/` directory a new engineer can read as a short book
(`INDEX.md`, `00-overview.md`) with exhaustive, traceable leaf specs behind it, plus a measured
fidelity score per module. The method combines what the 2024-2026 literature found works: hierarchical
specs verified by reconstruction (PROOF), blind reimplementation as the oracle (AfterVibe), code-derived
probes with a fixed held-out set (Fidelity Probes), confidence-tagged claims with traceability (Reversa),
language-neutral specs (Code2Text2Code), three-level verification of worker reports (Rebuild Dossier),
agent-neutral self-contained files (spec portability), and an implicit-decisions checklist (rebuild
test). `references/research-basis.md` maps every rule to its source.

You are the orchestrator. You run scripts, dispatch workers with the briefs in `references/briefs.md`,
read gate output, and decide. You do not write specs yourself (workers do, independently, which is
what makes validation meaningful), and you do not trust a worker's summary over a script's result.

## Inputs and defaults

- Target: the current repo, or a subsystem the user names. Scope is set by `inventory.py --include GLOB`
  (repeatable); files outside it remain in the inventory as context but are never sharded or specified.
  Specs go to `<repo>/specs/` unless the user names another directory. Never commit; never modify source.
- Modes: full (default), `--update` (re-extract only modules whose files changed since the recorded
  commit), `--validate-only` (probe existing specs without re-extracting), `--no-rebuild`.
- Budget tier comes from in-scope source LOC (`inventory.py`): S < 15k, M < 150k, L above. Tell the user
  the tier and the rough agent count before fan-out (formula in Phase 0). Tier L without a scope means
  hundreds of agents: say the estimate, run Phases 0-1 on the whole repo (the survey and shard plan are
  cheap and useful on their own), then run Phases 2-7 subsystem by subsystem in the reading order the
  Surveyor proposes, reporting after each, unless the user said to run everything.
- Set `SKILL_DIR` to this skill's absolute directory, `REPO` to the repo root, `SPECS` to the output
  dir, `SCRATCH` to your scratchpad. Every command below uses those.

## Phase 0: preflight (you, no workers)

```
python3 $SKILL_DIR/scripts/inventory.py $REPO --out $SPECS/_meta/inventory.json [--include GLOB ...] [--exclude GLOB ...]
```
Read the summary: tier, languages, test count, entry hints, build hints, and `largest_in_scope_files`.
Any file over ~4000 LOC must be split into line ranges before sharding:
`python3 $SKILL_DIR/scripts/split_file.py $REPO <path> --max-loc 3500` prints ready-to-use
`"path:START-END"` entries cut at definition boundaries; give them to the Surveyor. Record `COMMIT=$(git -C $REPO
rev-parse HEAD)`. If the tree is dirty, say so; specs are stamped with a commit and a dirty tree makes
freshness meaningless. Confirm the test command from build hints actually runs (try it once, with a
timeout); rebuilds need it and `04-operations.md` cites it.

Record how to run the project's code in `$SPECS/_meta/env.md`: interpreter, environment variables
(anything that avoids network calls at import), the test command, and the baseline failures. Install
the project's declared test environment (extras, dependency groups, dev requirements) rather than
chasing import errors one package at a time, and confirm the scoped tests collect with no import
errors. Workers get this file through `{{RUN_ENV}}` and use it to execute what they would otherwise
guess.

Agent estimate: 1 Surveyor + 4 cross-cutting + M extractors + M probers + M answerers + M judges per
round + revisers for failing modules + rebuilders. For M modules and R rounds that is roughly
5 + 2M + 2M·R + 0.5M·(R-1) + rebuilds. Say the number.

If `$SPECS/_meta/modules.json` already exists and the user did not ask for a fresh run, switch to
`--update`: `python3 $SKILL_DIR/scripts/changed_modules.py $SPECS --repo $REPO` lists the modules to
re-extract and new unassigned files to re-shard. Everything else in the pipeline is the same, scoped to
those modules (their probes are re-generated too, because the code changed).

## Phase 1: survey and shard (1 worker, then gate G1)

Workers are dispatched the same way in every phase: render the brief, then launch the agent with a
one-line prompt.
```
python3 $SKILL_DIR/scripts/render_briefs.py --role <role> [--module ID | --all-modules | --kind K] [--round N] [--snapshot DIR] \
    --specs $SPECS --repo $REPO --scratch $SCRATCH
```
It prints `<role> <module> <path>` per brief. Agent prompt: "Your complete instructions are in <path>.
Read that file first and follow it exactly." Never paste or hand-edit brief text: the renderer fills
the file lists, test lists, scope notes, and rounds, and refuses to write a brief with a gap.

Record every launch and completion in the dispatch log, so a container restart (which stops every
running subagent and wipes your memory of the batch) costs a resume, not a re-run:
```
python3 $SKILL_DIR/scripts/dispatch.py add --specs $SPECS --role <role> --module <id> --round N --brief <path> --agent <agentId>
python3 $SKILL_DIR/scripts/dispatch.py done --specs $SPECS --agent <agentId>       # on its completion notification
python3 $SKILL_DIR/scripts/dispatch.py next --specs $SPECS --cap 18                # queued briefs to launch now
python3 $SKILL_DIR/scripts/dispatch.py running --specs $SPECS                      # after a restart: resume each
```
After a restart, send each running agent a SendMessage to its id saying it was interrupted and should
check its output file and continue; re-create (fresh launch of the same brief) only agents whose resume
fails.

Dispatch the Surveyor (`--role surveyor`). When it returns, run:
```
python3 $SKILL_DIR/scripts/check_shards.py --inventory $SPECS/_meta/inventory.json --modules $SPECS/_meta/modules.json --out $SPECS/_meta/shards-report.json
```
Unassigned or multiply-assigned files, or a module over 6000 LOC at error level, go back to the
Surveyor with the exact list. Do not patch `modules.json` by hand unless the fix is a single obvious
glob; the Surveyor holds the rationale. Tier L: if the Surveyor returns more than 40 modules, group them
into subsystems in `survey.md` and run the remaining phases subsystem by subsystem so each fan-out stays
under ~12 concurrent workers.

`shards-report.json` has `module_paths`: the explicit file list per module. Use it to fill `{{FILES}}`
in briefs rather than globs, so no worker has to re-derive scope.

## Phase 2: extract (M + 4 workers in parallel, then gates G2, G3, G5)

Dispatch, in one message, one Extractor per module (`--role extractor --all-modules`) and, right
behind them in the queue, one Prober per module (Phase 4 step 1: probers read only code, so they need
not wait). Cross-cutting files come after (Phase 2b), because they index the module specs. Launch at most ~12 at once; queue the rest and dispatch the
next batch as results arrive. Workers are independent by design: none reads another's output.

When all return:
```
python3 $SKILL_DIR/scripts/gate.py $SPECS --repo $REPO
```
Before sending a G3 failure anywhere, open two of the flagged items in the spec and confirm they are
really absent; a gate false positive that a worker "fixes" bends correct specs toward the checker.
Send every gate failure back to the worker that wrote the file: SendMessage to its agent id (from
`dispatch.py`), with the failing lines or the uncited list. It still holds the module in context, so
the fix costs minutes instead of a re-read. Re-dispatch a fresh worker only if the resume fails.
- G2 lint errors: send the owning extractor the error lines. Lint is strict on
  purpose; an unresolvable ref or a duplicate ID is how specs rot.
- G3 coverage below threshold: send that extractor the uncited files and unmentioned symbols. "Trivial" files must be named as such in Scope and boundaries, not ignored.
- G5 discrepancies: a worker reported outputs that do not exist or counts that do not match. Send it
  the discrepancy; its output is untrusted until the report verifies.

Spot check (`references/validation.md` section 4): per module, open two random `{confirmed}` claims at
their refs. A miss sends the module back with the miss named. This is cheap and it changes how
extractors behave.

## Phase 2b: cross-cutting index files (after module specs pass G2 and G3; then G6)

Dispatch `--role crosscut --kind interfaces --kind data --kind config --kind operations` (drop data or
operations when the Surveyor says the scope has none). These files index the module specs by claim ID
and add only facts no module owns. Then run
`python3 $SKILL_DIR/scripts/check_ownership.py $SPECS --repo $REPO` (G6): a cross-cutting file in which
more than 20% of claims restate module-owned lines without a pointer, or a module spec in which more
than 10% of claims are about another module's lines, goes back to its writer. One fact, one owner is
what keeps revisions from leaving stale copies behind.

## Phase 3: reconcile (pair judges in parallel, a script applies edits, then 1 Reconciler; G2)

First run `python3 $SKILL_DIR/scripts/find_overlaps.py $SPECS`: it lists claim pairs from different
files that cite overlapping lines, near-duplicates with differing values first. That worklist is how
the Reconciler finds contradictions; reading thousands of claims for them does not work. Then:
1. Render pair judges (`--role pairjudge`, one per 60 rows; `--set SLICE_SIZE=N` to change) and
   dispatch them in parallel. They only write decisions; they never edit specs.
2. `python3 $SKILL_DIR/scripts/apply_claim_edits.py $SPECS` applies every edit by claim ID (the only
   writer, so parallel judges cannot race) and appends unresolvable pairs to `_meta/questions.md`.
   A claim edited differently by two judges is left untouched and listed in
   `_meta/reconcile/conflicts.json`; resolve each by choosing the variant that points straight at the
   owning claim, then re-run. Fix any reported pointer chains the same way. Re-run lint.
3. Dispatch the Reconciler: it turns questions into gaps, adds claim-ID cross-links,
writes `00-overview.md`, `_meta/gaps.md`, `_meta/questions.md`, and a first `INDEX.md`. Re-run `gate.py`.
Read `00-overview.md` yourself as the intended reader (new engineer, 15 minutes). If the first
paragraph does not say what the system is for, or a main path skips a module on it, send it back.

## Phase 4: probe (M probers, then M answerers, then M judges; gate G4)

Full protocol in `references/validation.md` section 2. In short:

1. Dispatch one Prober per module (code-only; the brief forbids reading specs). N_PROBES = 25 (tier L:
   20). Then:
   ```
   python3 $SKILL_DIR/scripts/score_probes.py $SPECS --assign-splits
   ```
   This validates probe files and fixes the held-out split for the life of the spec. Spot-check five
   probes per module for observability and citation; re-run a Prober whose probes do not hold up.
2. Build the spec-only snapshot (no source, no reference answers):
   ```
   python3 $SKILL_DIR/scripts/snapshot_for_answerers.py $SPECS --out $SCRATCH/spec-snapshot-round-1
   ```
3. Dispatch one Answerer per module pointing at the snapshot (`{{SPEC_SNAPSHOT}}`), round 1.
4. Dispatch one Judge per module (sees probes with reference answers plus the answers; may open code
   only to validate a reference).
5. Score:
   ```
   python3 $SKILL_DIR/scripts/gate.py $SPECS --repo $REPO --round 1
   ```
   Probes judged `probe_invalid` with evidence get their reference corrected once with
   `scripts/correct_probe.py` (logged) before the next round.
   `_meta/validation-report.md` has the table; `_meta/revise/round-1/<module>.jsonl` has revision-split
   failures only. The held-out failures exist in the judgments but are never handed to a writer.

## Phase 5: revise (per failing module, up to 3 rounds)

For each module not `validated`: copy its spec to `_meta/rounds/round-1/<module>.md`, dispatch a
Reviser with the failures file, re-run lint, then re-run Answerer (fresh snapshot) and Judge for that
module as round 2, and score with `--round 2`. Repeat to round 3 at most. Stop early per module when
validated or when the report says REGRESSION (restore the snapshot; keep the earlier status). Probes
never change between rounds; only the spec does. If more than 25% of a module's probes are judged
invalid, the Prober failed: re-run it and restart that module's loop.

Why the ceiling: AWS measured repair regression; past three rounds, revisions tend to trade one
failure for another. A module that will not validate is reported as provisional or weak with its
failing probe categories named, which is itself a finding about the code's legibility.

## Phase 6: rebuild (optional, strongest evidence; skip with --no-rebuild)

Eligibility and protocol in `references/validation.md` section 3. For each selected module: copy the
repo without `.git` to `$SCRATCH/rebuild-<module>/`, copy `specs/` in, delete the module's in-scope
files, dispatch the Rebuilder brief with the test command. Score is tests passed over total. The
Rebuilder's `guesses` and `spec_bugs` are spec defects: feed them to a Reviser as an extra failures
file and re-score probes for that module so regression is still watched. Nothing from the scratch copy
is ever copied back.

## Phase 7: adversarial audit (first run on a repo, or before anyone reviews specs instead of code)

The gates measure agreement among workers who share one method. The audit attacks the result from
outside it, with briefs in `references/audit.md` (rendered like any other) and one scorer.
1. Sample: `scripts/sample_claims.py $SPECS --per-module 12 --out $SPECS/_meta/audit/claims.jsonl`
   and `scripts/score_audit.py $SPECS --round <last> --make-judge-sample --n 40`.
2. Control: `scripts/snapshot_for_answerers.py $SPECS --out $SCRATCH/control --questions-only`, then
   dispatch `--role control --set CONTROL_DIR=$SCRATCH/control` and one Judge per module with
   `--round 0`. Prior knowledge is real for well-known projects; the validation report then shows each
   module's no-spec fidelity and the spec's lift over it.
3. Dispatch per module `--role falsifier --set SAMPLE_FILE=<claims.jsonl>` and `--role omission`; once
   `--role judge-auditor --set SAMPLE_FILE=<judge-sample.jsonl>`, `--role redteam`, and `--role reader
   --set READER_SCENARIO="<the system's most important request path>"`, then `--role lifecycle-checker`
   with the same scenario after the reader finishes.
4. `scripts/score_probes.py $SPECS --round <last>` (to pick up the control column), then
   `scripts/score_audit.py $SPECS --round <last>`. `_meta/audit-report.md` gives PASS or the failing
   checks. Each failure is a class of defect: fix the class (brief, gate, or script), log it in
   `references/learnings.md` with a self-test case, re-run the affected phases, and audit again.

## Phase 8: finalize and report

```
python3 $SKILL_DIR/scripts/apply_status.py $SPECS      # stamps status/fidelity in frontmatter, refreshes INDEX table
python3 $SKILL_DIR/scripts/collect_defects.py $SPECS   # _meta/suspected-defects.md for the human review
python3 $SKILL_DIR/scripts/gate.py $SPECS --repo $REPO --round <last>
```
Dispatch the Reconciler once more only if revisions touched cross-module facts (it re-checks
contradictions and refreshes `gaps.md`); otherwise regenerate `gaps.md` and `confidence-report.md`
yourself from the lint, coverage, and validation JSON, since those are mechanical. Then report to the
user in the format of `references/validation.md` section 6: verdict line, per-module table, top five
gaps, open questions, cost spent, limitations (section 7, stated plainly), and `specs/INDEX.md` as the
entry point. Do not commit; say the specs are uncommitted and offer to.

## Operating rules

- **Scripts over summaries.** A worker's reply is a claim. `gate.py` is evidence. The files are truth.
  When they disagree, the files win and the worker is re-run.
- **Independence is the instrument.** Extractors do not read other specs. Probers do not read specs.
  Answerers do not read code. Judges do not edit. Rebuilders cannot see the original. Breaking any of
  these to "save time" makes the fidelity number meaningless; the whole point of the output is that
  the number can be believed.
- **Honest status.** `status:` is set by `apply_status.py` from measured numbers, never typed. A
  module with zero gaps on a critical path is more likely overconfident than transparent; say so.
- **Never modify source.** Workers write under `$SPECS` and `$SCRATCH` only. Secrets found in code are
  redacted to `[REDACTED]` plus a gap; lint fails any spec containing a credential-shaped literal.
- **Agent-neutral output.** No model or tool names in any spec; lint fails claims that mention them.
  The specs must work for a human reader and for any future agent fed only the files.
- **Stable IDs.** Claim IDs are never renumbered or reused. Revisions rewrite text in place or append.
- **Freshness.** Every file is stamped with the commit. Lint warns on drift; `--update` is the fix.
- **Concurrency.** The harness caps concurrent subagents (20 by default; a launch over the cap fails
  with "Concurrent subagent limit reached" and must not be retried blindly). Keep the briefs that are
  rendered but not yet launched in `_meta/queue.txt` (one brief path per line), launch up to the cap
  minus two in one message, and launch the next queued brief each time a completion notification
  frees a slot. Probers depend only on code, so queue them right behind the extractors instead of
  waiting for reconciliation. Do not poll. Never run two workers for the same module and role at once.
- **Cost honesty.** Report agents launched and rounds run. If you stopped early (budget, repeated
  regression, a module that cannot be sharded), say which phase and why.

## Files

- `references/briefs.md`: the worker briefs, rendered to files by `render_briefs.py`; never pasted by hand.
- `references/templates.md`: claim grammar, confidence rules, precision ladder, writing rules, every
  file template, worker report format. Workers read this; you should too, once.
- `references/implicit-decisions.md`: what implementers invent when a spec is silent.
- `references/validation.md`: gates, thresholds, probe loop, rebuild loop, spot checks, final report,
  limitations.
- `references/research-basis.md`: which paper each rule comes from and what it found.
- `references/learnings.md`: every failure class found in real runs and grading, and the fix that
  removed it. Read before changing this skill; run `scripts/selftest.py` after changing any script.
- `scripts/`: stdlib Python 3.9+, deterministic, each prints a one-line summary to stderr.
  Planning: `inventory.py`, `split_file.py`, `check_shards.py`, `changed_modules.py`.
  Dispatch: `render_briefs.py`, `dispatch.py`, `snapshot_for_answerers.py`.
  Gates: `lint_specs.py`, `coverage.py`, `check_ownership.py`, `score_probes.py`, `verify_reports.py`, `gate.py`.
  Reconcile: `find_overlaps.py`, `apply_claim_edits.py`, `collect_defects.py`.
  Audit: `sample_claims.py`, `score_audit.py` (briefs in `references/audit.md`).
  Rebuild: `prepare_rebuild.py`, `score_rebuild.py`. Finalize: `apply_status.py`, `collect_defects.py`.
  Gate regression tests: `selftest.py`.
