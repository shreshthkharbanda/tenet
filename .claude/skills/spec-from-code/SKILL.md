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
  dir, `SCRATCH` to your scratchpad, and `EVAL=$SCRATCH/eval`. Every command below uses those.
- `TRANSCRIPTS` is where the harness keeps subagent transcripts (Claude Code:
  `~/.claude/projects/<project>/<session>/subagents/`; it is the directory the Agent tool's
  `output_file` links into). G5 reads them to check what workers actually opened.

## Phase 0: preflight (you, no workers)

```
python3 $SKILL_DIR/scripts/inventory.py $REPO --out $SPECS/_meta/inventory.json --eval $EVAL [--include GLOB ...] [--exclude GLOB ...]
```
`$EVAL` holds everything that defines or reveals the score: probes with reference answers, answers,
judgments, validation reports, probe corrections, the judge-audit sample, and the reports of the roles
that touch them. It must sit outside the repo and the specs dir (inventory refuses otherwise), so a
writer's recursive search of either never reaches a held-out answer. Never give `$EVAL` to a writer.
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
guess. Record the same thing for scripts in `_meta/run.json` (written by inventory.py; add the keys):
`"python"` (interpreter), `"run_cwd"` (a scratch working directory), `"run_env"` (a dict of
environment variables). `gate.py` uses them to re-run evidence checks (G7).

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
fails. `dispatch.py unfinished --specs $SPECS [--snapshot DIR]` is the ground truth for what is left
(rendered briefs with no worker report), whether or not every launch was logged; check it before
scoring any phase.

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
python3 $SKILL_DIR/scripts/gate.py $SPECS --repo $REPO --transcripts $TRANSCRIPTS
```
Always pass `--transcripts` to `gate.py` when the harness keeps them: without it, isolation rests on
what workers say they read. Before sending a G3 failure anywhere, open two of the flagged items in the spec and confirm they are
really absent; a gate false positive that a worker "fixes" bends correct specs toward the checker.
Send every gate failure back to the worker that wrote the file: SendMessage to its agent id (from
`dispatch.py`), with the failing lines or the uncited list. It still holds the module in context, so
the fix costs minutes instead of a re-read. Re-dispatch a fresh worker only if the resume fails.
- G2 lint errors: send the owning extractor the error lines. Lint is strict on
  purpose; an unresolvable ref or a duplicate ID is how specs rot.
- G3 coverage below threshold: send that extractor the uncited files, unmentioned symbols, uncited line
  stretches (line coverage under 60% means part of the range was never specified, the usual sign of a
  worker that ran out of context), and unanchored claim IDs (refs that point away from what the claim
  says), all listed in `_meta/traceability.md`. "Trivial" files must be named as such in Scope and boundaries, not ignored.
- G5 discrepancies: a missing report for a dispatched worker, outputs that do not exist or predate
  the launch, counts that do not match, or an access the role forbids (seen in the transcript). Send
  the worker the discrepancy; its output is untrusted until the report verifies. A writer that
  touched `$EVAL` contaminates its module's held-out score: discard its output and re-dispatch. A
  finding that is harmless on evidence (an `ls` of a file that did not exist yet) may be waived by a
  row in `$EVAL/g5-waivers.jsonl` (outside the specs dir, so no worker can waive its own findings) with
  a specific `match` (12+ characters), the reason and the evidence; waivers print in every G5 run.

Spot check (`references/validation.md` section 4): per module, open two random `{confirmed}` claims at
their refs. A miss sends the module back with the miss named. This is cheap and it changes how
extractors behave.

## Phase 2b: cross-cutting index files (after module specs pass G2 and G3; then G6)

Dispatch `--role crosscut --kind interfaces --kind data --kind config --kind operations` (drop data or
operations when the Surveyor says the scope has none). These files index the module specs by claim ID
and add only facts no module owns. Then run
`python3 $SKILL_DIR/scripts/check_ownership.py $SPECS --repo $REPO` (G6): a cross-cutting file in which
more than 20% of claims restate module-owned lines without a pointer, or a module spec in which more
than 10% of claims are about another module's lines, goes back to its writer. A pointer counts only
when the claim it names is about the same thing (overlapping lines or a shared backticked literal):
tacking any owner ID onto a restatement does not. One fact, one owner is what keeps revisions from
leaving stale copies behind.

## Phase 3: reconcile (pair judges in parallel, a script applies edits, then 1 Reconciler; G2)

First run `python3 $SKILL_DIR/scripts/find_overlaps.py $SPECS`: it lists claim pairs that cite
overlapping lines, from different files or the same one (a corrected claim added beside the old one),
plus wide refs that share an identifier, near-duplicates with differing values first. That worklist is how
the Reconciler finds contradictions; reading thousands of claims for them does not work. Then:
1. Render pair judges (`--role pairjudge`, one per 60 rows; `--set SLICE_SIZE=N` to change) and
   dispatch them in parallel. They only write decisions; they never edit specs.
2. `python3 $SKILL_DIR/scripts/apply_claim_edits.py $SPECS` applies every edit by claim ID (the only
   writer, so parallel judges cannot race) and appends unresolvable pairs to `_meta/questions.md`.
   A claim edited differently by two judges is left untouched and listed in
   `_meta/reconcile/conflicts.json`; resolve each by writing the chosen variant (the one that points
   straight at the owning claim) to a new decisions file, then re-run. Applied files are recorded in
   `_meta/reconcile/ledger.json` and never replayed, so a later reviser's rewrite of a claim is not
   reverted by an old decision; never edit an applied file. Fix any reported pointer chains the same
   way. Re-run lint.
3. Dispatch the Reconciler: it turns questions into gaps, adds claim-ID cross-links,
writes `00-overview.md`, `_meta/gaps.md`, `_meta/questions.md`, and a first `INDEX.md`. Re-run `gate.py`.
Read `00-overview.md` yourself as the intended reader (new engineer, 15 minutes). If the first
paragraph does not say what the system is for, or a main path skips a module on it, send it back.

## Phase 3b: evidence sweep (verifiers; gate G7)

Every `{confirmed}` claim in a module's normative sections gets executed evidence before probing. Run
`python3 $SKILL_DIR/scripts/render_briefs.py --role verifier --module <id> ...` per module: it splits
the module's unbacked confirmed normative claims into chunks of 25 and renders one brief per chunk.
Dispatch them like extractors. Each verifier writes `_meta/evidence/<module>/check_<ID>.py` per
claim (drives the public entry point, asserts what the claim states, then attacks what it leaves
unsaid: dependency failure, wrong-typed input, early cancel, sibling entry points, a second instance)
and corrects wrong claims through `decisions-verify-<module>-<chunk>.jsonl`. When a module's
verifiers finish, run `apply_claim_edits.py` (only complete decision files: an applied file must not
change), then `gate.py` (G7 re-runs every check in parallel and lists failing, stale and orphan
checks). Why it is not optional: on LiteLLM, reading-based claims that had passed probes and a revision
round were 26% wrong when executed (73 of 274 corrected), and a blind falsification sample after the
sweep found 0 false claims in verified modules against 12% in unverified ones (L61, L66). Cost: about
one verifier per 25 confirmed claims (tier M: ~6 per module). Tier L: sweep critical modules first.
G7 also makes the spec maintainable: after a code change, `gate.py` lists exactly the claims whose
checks now fail.

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
   python3 $SKILL_DIR/scripts/gate.py $SPECS --repo $REPO --round 1 --transcripts $TRANSCRIPTS
   ```
   Probes judged `probe_invalid` with evidence get their reference corrected once with
   `scripts/correct_probe.py` (logged, evidence must cite code; a held-out probe needs
   `--allow-holdout`) before the next round. Until then a held-out `probe_invalid` counts as a miss.
   The scorer checks verdicts: agree on an empty answer is an error, 3+ agrees whose answer shares
   none of the reference's literals send that module's judgments back for strict re-judging, and
   answers copying reference phrasing that is not in the spec mean the answerer read code.
   `$EVAL/validation-report.md` has the full report; `_meta/validation-summary.md` has the table only
   (safe for writers); `_meta/revise/round-1/<module>.jsonl` has revision-split failures only. The
   held-out failures exist only in `$EVAL` and are never handed to a writer.

## Phase 5: revise (per failing module, up to 3 rounds)

Before the first revision round, run the universal-claim falsification pass on every module:
`scripts/sample_claims.py $SPECS --universal-only --per-module 8 --out $SPECS/_meta/audit/round-N/universal.jsonl`,
then one `--role falsifier --set SAMPLE_FILE=<that file>` per module. Universal claims (always, never,
unless, only) are where writers overreach; false and imprecise verdicts join that module's failures
file (category `falsifier`) so the Reviser fixes them with the probe failures.


Build each module's failures file from every source with
`python3 $SKILL_DIR/scripts/build_revise.py $SPECS --repo $REPO --round N` (probe failures and notes,
falsifier and omission findings, lint warnings, rebuild guesses). For each module not `validated`, and
for any validated module whose file has falsifier, omission, or rebuild rows: copy its spec to
`_meta/rounds/round-1/<module>.md`, dispatch a Reviser with the failures file, re-run lint, then re-run Answerer (fresh snapshot) and Judge for that
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
1. Sample: `scripts/sample_claims.py $SPECS --per-module 12 --out $SPECS/_meta/audit/round-N/claims.jsonl`
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
   `scripts/score_audit.py $SPECS --round <last>`. Every audit role is rendered with `--round N` and
   writes under `_meta/audit/round-N/` (the judge sample and judge audit under `$EVAL/audit/round-N/`),
   so a later round's audit never overwrites or moves an earlier one; never move a worker's outputs by
   hand, since its report records their paths. `_meta/audit-report.md` gives PASS or the failing
   checks. Each failure is a class of defect: fix the class (brief, gate, or script), log it in
   `references/learnings.md` with a self-test case, re-run the affected phases, and audit again.

## Phase 8: finalize and report

```
python3 $SKILL_DIR/scripts/apply_status.py $SPECS      # stamps status/fidelity in frontmatter, refreshes INDEX table
python3 $SKILL_DIR/scripts/collect_defects.py $SPECS   # _meta/suspected-defects.md for the human review
python3 $SKILL_DIR/scripts/gate.py $SPECS --repo $REPO --round <last> --transcripts $TRANSCRIPTS
cp $EVAL/validation-report.md $SPECS/_meta/   # only now: no writer runs after this point
```
`apply_status.py` reads `_meta/status.json`, so run `gate.py` before it: a module is never stamped
`validated` over a failed G4 or G5.
Dispatch the Reconciler once more only if revisions touched cross-module facts (it re-checks
contradictions and refreshes `gaps.md`); otherwise regenerate `gaps.md` and `confidence-report.md`
yourself from the lint, coverage, and validation JSON, since those are mechanical. Then report to the
user in the format of `references/validation.md` section 6: verdict line, per-module table, top five
gaps, open questions, cost spent, limitations (section 7, stated plainly), and `specs/INDEX.md` as the
entry point. Do not commit; say the specs are uncommitted and offer to.

## Phase 9: reader site (M narrators, gate G8, then the site)

The specs are the source of truth; the site is how people read them. A module spec is a ledger of
hundreds of claims, which nobody reads front to back. Each module gets a **story** written over its
ledger (`references/story.md`): the thesis, the module in one minute, a When/Then table, three to six
illustrated sections and the traps. Every sentence cites the claims it rests on, and G8 rejects any
name or number those claims or their code do not contain, so a story selects and explains but never
adds. The site shows the story above the ledger, and every claim opens onto the lines it cites.
```
python3 $SKILL_DIR/scripts/render_briefs.py --role narrator --all-modules --specs $SPECS --repo $REPO --scratch $SCRATCH
# dispatch one narrator per module (queue as usual); each runs check_story.py until it passes
python3 $SKILL_DIR/scripts/check_story.py $SPECS                       # G8 over every story
python3 $SKILL_DIR/scripts/build_site.py $SPECS --out $SCRATCH/site    # data/ + index.html
```
A story that fails G8 is left out of the site (the chapter shows its ledger only) and reported.
Before anyone reviews from the site, run the story audit in `references/audit.md` (a story judge per
module checks sentences against the claims they cite; story-only readers answer the held-out probes,
and a story that leads a reader to a contradicted answer goes back to its narrator).
To publish: where the host offers a page publisher, publish `site/index.html` with every
`site/data/*.json` as supporting files (relative `fetch` loads them); elsewhere build with
`--standalone` and serve the folder over HTTP. Rebuild the site after every revision round: it is
compiled from the specs and never edited by hand.

## Operating rules

- **Scripts over summaries.** A worker's reply is a claim. `gate.py` is evidence. The files are truth.
  When they disagree, the files win and the worker is re-run.
- **Independence is the instrument.** Extractors do not read other specs. Probers do not read specs.
  Answerers do not read code. Judges do not edit. Rebuilders cannot see the original. Breaking any of
  these to "save time" makes the fidelity number meaningless; the whole point of the output is that
  the number can be believed.
- **Honest status.** `status:` is set by `apply_status.py` from measured numbers, never typed. A
  module with zero gaps on a critical path is more likely overconfident than transparent; say so.
- **The eval dir is the answer key.** Only probers, answerers, the control, judges and the judge
  auditor are ever given `$EVAL`; nothing a writer reads mentions it.
- **Workers only write files.** Every brief ends with a boundaries footer, and G5 fails a worker whose
  transcript shows a publish, a connector call, a message, a schedule or a push (L74). If one happened,
  tell the user what was published or sent; deleting it is their call.
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
- `references/story.md`: the chapter story format, writing rules, figure syntax and gate G8.
- `assets/site/`: the reader site (index.html template, CSS, JS) that `build_site.py` inlines.
- `references/learnings.md`: every failure class found in real runs and grading, and the fix that
  removed it. Read before changing this skill; run `scripts/selftest.py` after changing any script.
- `scripts/`: stdlib Python 3.9+, deterministic, each prints a one-line summary to stderr.
  Planning: `inventory.py`, `split_file.py`, `check_shards.py`, `changed_modules.py`.
  Dispatch: `render_briefs.py`, `dispatch.py`, `snapshot_for_answerers.py`.
  Gates: `lint_specs.py`, `check_coverage.py`, `check_ownership.py`, `score_probes.py`, `verify_reports.py`, `gate.py`.
  Reconcile: `find_overlaps.py`, `apply_claim_edits.py`, `collect_defects.py`.
  Revise: `build_revise.py`, `correct_probe.py`.
  Audit: `sample_claims.py`, `score_audit.py` (briefs in `references/audit.md`).
  Rebuild: `prepare_rebuild.py`, `score_rebuild.py`. Finalize: `apply_status.py`, `collect_defects.py`.
  Reader site: `check_story.py` (G8), `site_data.py`, `build_site.py`.
  Gate regression tests: `selftest.py`.
