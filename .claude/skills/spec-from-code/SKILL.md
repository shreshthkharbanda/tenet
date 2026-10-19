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

- Target: the current repo, or a path/subsystem the user names (`--scope`). Specs go to `<repo>/specs/`
  unless the user names another directory. Never commit; never modify source.
- Modes: full (default), `--update` (re-extract only modules whose files changed since the recorded
  commit), `--validate-only` (probe existing specs without re-extracting), `--no-rebuild`.
- Budget tier comes from in-scope source LOC (`inventory.py`): S < 15k, M < 150k, L above. Tell the user
  the tier and the rough agent count before fan-out (formula in Phase 0). Proceed without waiting
  unless the tier is L and the user gave no scope; then say the estimate and proceed with the plan the
  Surveyor produces, since the user asked for the whole repo.
- Set `SKILL_DIR` to this skill's absolute directory, `REPO` to the repo root, `SPECS` to the output
  dir, `SCRATCH` to your scratchpad. Every command below uses those.

## Phase 0: preflight (you, no workers)

```
python3 $SKILL_DIR/scripts/inventory.py $REPO --out $SPECS/_meta/inventory.json [--exclude GLOB ...]
```
Read the summary: tier, languages, test count, entry hints, build hints. Record `COMMIT=$(git -C $REPO
rev-parse HEAD)`. If the tree is dirty, say so; specs are stamped with a commit and a dirty tree makes
freshness meaningless. Confirm the test command from build hints actually runs (try it once, with a
timeout); rebuilds need it and `04-operations.md` cites it.

Agent estimate: 1 Surveyor + 4 cross-cutting + M extractors + M probers + M answerers + M judges per
round + revisers for failing modules + rebuilders. For M modules and R rounds that is roughly
5 + 2M + 2M·R + 0.5M·(R-1) + rebuilds. Say the number.

If `$SPECS/_meta/modules.json` already exists and the user did not ask for a fresh run, switch to
`--update`: `python3 $SKILL_DIR/scripts/changed_modules.py $SPECS --repo $REPO` lists the modules to
re-extract and new unassigned files to re-shard. Everything else in the pipeline is the same, scoped to
those modules (their probes are re-generated too, because the code changed).

## Phase 1: survey and shard (1 worker, then gate G1)

Dispatch the Surveyor brief. When it returns, run:
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

Dispatch, in one message, one Extractor per module plus the four cross-cutting extractors
(Interfaces, Data, Config, Operations). Launch at most ~12 at once; queue the rest and dispatch the
next batch as results arrive. Workers are independent by design: none reads another's output.

When all return:
```
python3 $SKILL_DIR/scripts/gate.py $SPECS --repo $REPO
```
- G2 lint errors: re-dispatch the owning extractor with the error lines pasted in. Lint is strict on
  purpose; an unresolvable ref or a duplicate ID is how specs rot.
- G3 coverage below threshold: re-dispatch that extractor in revise mode with the uncited files and
  unmentioned symbols. "Trivial" files must be named as such in Scope and boundaries, not ignored.
- G5 discrepancies: a worker reported outputs that do not exist or counts that do not match. Re-run it;
  its output is untrusted until the report verifies.

Spot check (`references/validation.md` section 4): per module, open two random `{confirmed}` claims at
their refs. A miss sends the module back with the miss named. This is cheap and it changes how
extractors behave.

## Phase 3: reconcile (1 worker, then G2)

Dispatch the Reconciler: it fixes cross-module contradictions from code, adds claim-ID cross-links,
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

## Phase 7: finalize and report

```
python3 $SKILL_DIR/scripts/apply_status.py $SPECS      # stamps status/fidelity in frontmatter, refreshes INDEX table
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
- **Concurrency.** Up to ~12 workers per batch, all `run_in_background: true`, dispatched in one
  message, results handled as notifications arrive. Do not poll. Do not run the same worker twice in
  parallel for one module.
- **Cost honesty.** Report agents launched and rounds run. If you stopped early (budget, repeated
  regression, a module that cannot be sharded), say which phase and why.

## Files

- `references/briefs.md`: the nine worker prompts; fill placeholders, paste verbatim.
- `references/templates.md`: claim grammar, confidence rules, precision ladder, writing rules, every
  file template, worker report format. Workers read this; you should too, once.
- `references/implicit-decisions.md`: what implementers invent when a spec is silent.
- `references/validation.md`: gates, thresholds, probe loop, rebuild loop, spot checks, final report,
  limitations.
- `references/research-basis.md`: which paper each rule comes from and what it found.
- `scripts/`: `inventory.py`, `check_shards.py`, `lint_specs.py`, `coverage.py`, `score_probes.py`,
  `verify_reports.py`, `snapshot_for_answerers.py`, `changed_modules.py`, `apply_status.py`,
  `gate.py`. Stdlib Python 3.9+, deterministic, each prints a one-line summary to stderr.
