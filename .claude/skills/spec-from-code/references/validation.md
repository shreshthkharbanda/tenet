# Validation protocol

Specs are claims. Nothing in a spec is trusted because a worker wrote it; it is trusted because a check
passed. Five mechanical gates, one probe loop, and one optional rebuild loop. Scripts live in
`scripts/`; every one is stdlib Python, deterministic, and prints a one-line summary on stderr.

Contents: 1 Gates · 2 Probe loop · 3 Rebuild loop · 4 Orchestrator spot checks · 5 Thresholds ·
6 Final report · 7 Known limitations (say these to the user)

## 1. Gates

| Gate | Script | Passes when | On failure |
|---|---|---|---|
| G1 shards | `check_shards.py` | every in-scope source file is in exactly one module; no module > 6000 LOC error-level | re-run Surveyor with the unassigned/multiply-assigned list |
| G2 lint | `lint_specs.py` | zero errors: grammar, unique IDs, refs resolve, sections present, no secrets, no tool mentions, cross-refs resolve | re-run the owning Extractor/Reviser with the error lines |
| G3 coverage | `coverage.py` | per module: >= 95% in-scope files cited, >= 85% public symbols mentioned | re-run Extractor in revise mode with the uncited list |
| G4 probes | `score_probes.py --round N` | per module held-out fidelity >= 0.90, zero held-out contradictions and >= 8 valid held-out probes (validated); >= 0.75 provisional. Errors: agree on an empty answer; 3+ agrees sharing none of the reference's literals; 70%+ answers copying reference phrasing absent from the spec; > 25% invalid in either split | Reviser round, see section 2; re-judge or re-answer per the error |
| G5 reports | `verify_reports.py --transcripts DIR` | every finished dispatch has its report; outputs exist and postdate the launch; role rules hold on the transcript (writers never touch `$EVAL` or snapshots; probers and judges read no spec text; answerers and the control stay in their snapshot; rebuilders stay in their copy and read no tests) | re-run that worker; a writer that touched `$EVAL` contaminates its module's held-out score |

`gate.py specs --repo . [--round N] [--transcripts DIR]` runs whatever has inputs and prints one
table; `_meta/status.json` holds the result. A gate whose inputs should exist never skips silently:
`--round` without probes is a FAIL, and G5 runs whenever anything was dispatched. Run it after every
phase. Trust the table over any worker's summary.

Freshness: every spec file carries `commit:`. Lint warns when it differs from HEAD; `--strict-fresh`
makes it an error. A spec for moved code is not a spec.

## 2. Probe loop (Fidelity Probes, adapted)

Why probes and not just tests: the existing test suite measures the code. Probes measure whether the
spec carries the information the code carries, including behavior no test pins.

1. **Probers** (code-only, per module) write N probes each with a reference answer and refs.
   N = 25 for tier S/M modules, 20 for tier L, never below 12. Run `score_probes.py --assign-splits`
   once: it validates the files and assigns `revision` / `holdout` deterministically by id hash
   (60/40). The held-out set is fixed for the life of the spec. Writers never see it: probes,
   answers, judgments and validation reports live in `$EVAL`, outside the specs dir and the repo.
2. **Snapshot** the specs for answerers: copy the spec text to `{{SCRATCH}}/spec-snapshot-round-N/` and
   write `_meta/probes/<module>.questions.jsonl` inside it containing only `id` and `question`.
   Answerers point at the snapshot; it contains no code and no reference answers.
3. **Answerers** (spec-only, per module) answer every probe or mark it unanswerable.
4. **Judges** (per module) produce verdicts.
5. `score_probes.py --round N --failures-for-revision` writes the report and
   `_meta/revise/round-N/<module>.jsonl` (revision-split failures only).
6. For every module below `validated`: snapshot its spec to `_meta/rounds/round-N/<module>.md`, run a
   **Reviser**, re-lint, then re-run Answerer + Judge for that module as round N+1 (the probes do not
   change; only the spec does).
7. Stop per module when: validated; or three revision rounds done; or held-out fidelity dropped by
   more than 2 points (REGRESSION: restore the snapshot from `_meta/rounds/` and keep the previous
   round's status). Repair regression is real (AWS measured it); do not chase the number.
8. Invalid probes: if a judge marks more than 25% of a module's probes `probe_invalid`, the prober
   failed; re-run the Prober for that module and start its loop again.

Probe quality spot check (orchestrator, before round 1): read five random probes per module. Each must
be observable, single-answer, and cite lines that actually contain the answer. If two of five fail,
re-run that Prober with the specific failures named.

## 3. Rebuild loop (round-trip; optional, strongest evidence)

A rebuild asks the direct question: can an implementer who has only the spec produce the behavior?

Eligibility: modules with `rebuild_candidate: true` and a test command that can run after replacing the
module's files. Tier S: all eligible modules. Tier M: all `critical` eligible modules plus a random 20%
of the rest, capped at 10. Tier L: at most 5, chosen by criticality.

Protocol per module (all mechanical except step 2):
1. `prepare_rebuild.py setup --specs $SPECS --repo $REPO --scratch $SCRATCH --module ID --test-cmd
   "<cmd with {junit}>" [--python-pkg PKG --python-exe <venv python>]`. It copies the repo without
   `.git` and the spec text without probes or answers, verifies the package under test resolves inside
   the copy (editable installs otherwise make the copy test the original), runs the baseline, removes
   the module (files deleted; line ranges replaced by a marker), and runs the tests again. It fails if
   removal breaks no baseline-passing test: such a rebuild cannot tell a good spec from a bad one.
   Choose the narrowest test command that covers the module; full suites waste minutes per run.
2. Render and dispatch the **Rebuilder** (`render_briefs.py --role rebuilder --module ID --test-cmd
   "<cmd>"`). It cannot see the original: no git, no files outside the copy.
3. `prepare_rebuild.py score --specs $SPECS --scratch $SCRATCH --module ID --test-cmd "<cmd>"`.
   The headline number is the recovery rate: of the baseline-passing tests that removal broke, the
   share the rebuild restored. Overall pass rate is reported too. The Rebuilder's own numbers are not
   used.
4. The `guesses`, `spec_bugs`, and `learned_from_test_failures` lists are spec defects: feed them to a
   Reviser as an extra failures file (same shape as revise jsonl, category `rebuild`), then re-score
   probes for that module as a new round so repair regression is still watched.

Interpretation: a rebuild that passes all tests proves the spec plus the tests are sufficient; the
Rebuild Dossier result (a rule-breaking agent passed every test) means it does not prove the spec alone
is. A rebuild that fails tells you exactly which claims are missing, which is the useful signal.

## 3b. Adversarial audit (Phase 7)

The audit has its own pass bar, stricter than the probe gate because it is aimed at the failures the
gate cannot see. Pass means every check below passes (thresholds live in `score_audit.py`):

| Check | Worker | Passes when |
|---|---|---|
| Falsification | falsifier per module, fixed random claim sample | high-severity false or imprecise claims are at most 5% of the sample |
| Omission | omission hunter per module, lists top behaviors before reading the spec | at least 80% of the top behaviors are stated precisely and none is contradicted |
| Judge reliability | judge auditor on a blind sample oversampling "agree" | at least 90% of verdicts reproduce and at most 5% of "agree" verdicts are rejected |
| Prior knowledge | control answerer with questions only, judged as round 0 | lift over the control is at least 30 points |
| Teachability | reader (spec only) explains a request path; checker traces it in code | no step is incorrect |
| Gate robustness | red team on a copy of the specs | every demonstrated exploit has a mechanical fix or a recorded decision |

## 4. Orchestrator spot checks

Scripts verify structure; you verify substance, cheaply:
- After extraction, for each module read two random `{confirmed}` claims, open the ref, and confirm
  the text follows from the lines. One miss: re-run that module with the miss named. The point is not
  the two claims; it is that extractors behave differently when they know refs get opened.
- After reconciliation, read `00-overview.md` end to end as the intended reader (an engineer new to
  the repo with 15 minutes). If a main path skips a module that is on it, or you cannot tell what the
  system is for from the first paragraph, send it back with the specific gap.
- Before reporting, open `_meta/gaps.md`. If a critical module has zero gaps, be suspicious: it is far
  more likely the extractor was overconfident than that the code was fully transparent. Say so.

## 5. Thresholds (defaults; the user may tighten)

| Measure | validated | provisional | weak |
|---|---|---|---|
| Held-out fidelity | >= 0.90 and 0 contradictions | >= 0.75 | < 0.75 |
| File coverage | >= 0.95 | >= 0.85 | below |
| Public symbol coverage | >= 0.85 | >= 0.70 | below |
| Rebuild recovery (informational) | >= 0.95 of removal-broken tests restored | >= 0.70 | below |

A module's `status:` in its frontmatter is set by the orchestrator from these, never by the writer.

## 6. Final report (what the user sees)

Lead with the one-line verdict: how many modules validated / provisional / weak, and whether the spec
set is ready to be reviewed instead of the code. Then:

| Module | Claims (c/i/g) | Files | Symbols | Held-out fidelity | Contradictions | Rebuild | Rounds | Status |

Then: the suspected defects (from `_meta/suspected-defects.md`, most consequential first), the five
most important gaps (from `_meta/gaps.md`, chosen for impact on the main paths), the contradictions
left as questions, the cost actually spent (agents launched, rounds run), and the
limitations below in one short paragraph. Point at `specs/INDEX.md` as the entry point. Do not commit.

## 7. Known limitations

- Isolation is instruction-based plus verification, not a sandbox. With transcripts, G5 sees every
  path a worker's tools touched, including paths inside shell commands and files listed by searches;
  it cannot see code reached indirectly (importing an installed package, a script that opens files
  it does not name). Without transcripts, isolation rests on self-reported read lists. Say which.
- Probes sample behavior; a validated module can still have unprobed gaps. The implicit-decisions
  checklist and symbol coverage reduce this; they do not eliminate it.
- Reference answers can be wrong; judges can mark `probe_invalid`, and invalid rates are reported.
- Symbol coverage is a regex heuristic per language; for languages without a pattern it falls back to
  file coverage only.
- Rebuild scores depend on the test suite's own coverage. Few tests, little signal.
- Everything here measures agreement between the spec and the code as it is. It does not know what the
  code should do. Gaps and questions are where that conversation starts.
