# Learnings log

Each entry is a class of failure found by running this skill on a real repository or by grading its
output adversarially, with the fix that removes the class (not the instance). Prefer fixes that are
mechanical (a script, a gate, a renderer) over fixes that are instructions, because instructions are
what failed in the first place. Read this before changing the skill, so a fix does not reintroduce a
class already removed.

Format: ID, where it was found, the class, the root cause, the fix, and how the fix is enforced.

## Iteration 0 (LiteLLM preflight; tenet dry runs)

**L01. Documented capability with no mechanism.** Found: LiteLLM preflight (1.2M source LOC, tier L).
SKILL.md promised scoping to a subsystem; no script supported it, so the only route was dozens of
`--exclude` globs. Fix: `inventory.py --include GLOB` marks everything else `in_scope: false` (kept as
context, never sharded). Enforced: every option SKILL.md names must name the script flag that
implements it; reviewers check this when editing SKILL.md.

**L02. Files larger than one extractor's budget.** Found: LiteLLM `router.py` is 16,278 lines (14.6k
LOC) in one class; the 6000-LOC module cap could not be met with whole-file globs, so the shard gate
was unsatisfiable. Fix: modules may own line ranges (`"path:START-END"`); `split_file.py` proposes
cuts only at definition boundaries (top level, or members of a top-level class, never inside a
function) with decorators kept attached; `check_shards.py` requires ranges of a file to be contiguous,
non-overlapping, and complete; `coverage.py` counts refs and public symbols per range;
`changed_modules.py` reports ranged files that changed (`resplit_files`) because line numbers shift.
Enforced: G1 fails on gaps, overlaps, ranges past EOF, and modules over the cap.

**L03. Isolation checks keyed to a directory name.** Found: running with a specs dir not named
`specs/` (LiteLLM run used `ll-specs/`). `verify_reports.py` matched the literal substring
`/specs/`, so prober blindness and answerer isolation were silently unchecked. Fix: checks resolve
every `files_read` path and compare against the real specs dir and the answerer's declared snapshot;
the snapshot must lie outside the repo and contain no source files; `snapshot_for_answerers.py`
refuses to write inside a git repo. Enforced: G5.

**L04. Orchestrator hand-fills briefs.** Found: planning the tier-L run (dozens of modules × 4 roles ×
rounds). Pasting multi-kilobyte briefs bloats the orchestrator's context and invites placeholder
drift (wrong file list, stale round). Fix: `render_briefs.py` renders every role from `briefs.md`
markers, fills placeholders from modules.json, the shard plan, and the inventory, and refuses to
write a brief with a placeholder left. The Agent prompt is one line pointing at the file. Answerer
briefs are written inside the snapshot so reading one's own brief does not break isolation.
Enforced: renderer exit status; SKILL.md dispatch steps use it.

**L05. Reference answers verified only by reading.** Found: tenet `report` prober dry run, which on
its own initiative compiled the module in scratch and ran throwaway harnesses, catching behaviors no
test pins (null handling, SARIF path normalization). Fix: the prober brief asks for execution in
`{{SCRATCH}}/probe-harness-<module>/` where cheap and records `verified_by`. Also adds an `edge`
boolean, because edge-path coverage cut across categories and could not be checked from `category`.

**L06. Whole-tree lint while siblings are mid-write.** Found: designing parallel extraction. A worker
linting all of `specs/` sees other workers' half-written files and either chases their errors or
learns to ignore lint. Fix: `lint_specs.py --only <file>`; cross-references that cannot be resolved
under `--only` become warnings. Full-tree lint is the orchestrator's job after the batch.

**L07. Inputs accepted but never consumed.** Found: LiteLLM iteration 1, rendering the Surveyor brief
with a scope note and the router.py cut points; the Surveyor template had no `{{SCOPE_NOTE}}`, so the
renderer accepted the note and dropped it without a word. The Surveyor would have sharded the whole
repository. Fix: `render_briefs.py` refuses an option whose placeholder is absent from the role's
template; the Surveyor and Reconciler templates now carry the scope, and the Surveyor brief explains
line-range entries and runs the shard gate itself. Enforced: renderer exit status.

**L08. Commit-level freshness cries wolf.** Found: tenet extractor dry run; HEAD moved mid-run (a
commit that only added this skill) and lint flagged the spec stale, training workers to ignore the
warning. Fix: lint diffs the spec's commit against HEAD (plus uncommitted changes) and warns only when
a cited file or an in-scope file changed. Enforced: G2.

**L09. Absolute test pass rates blame the spec for the environment.** Found: LiteLLM router tests,
47 of 1716 failing on untouched code in a fresh venv. Fix: `score_rebuild.py` scores only tests that
passed on the untouched copy; `prepare_rebuild.py` runs the baseline itself; the headline is the
recovery rate over tests that removing the module broke. The Rebuilder no longer reports pass counts.

**L10. Copies that test the original.** Found: LiteLLM installed editable; `import litellm` from any
directory that does not shadow it resolves to the original checkout, so a rebuild in a copy could pass
without the rebuilt code ever running. Fix: `prepare_rebuild.py --python-pkg` checks import
resolution, and the deletion check fails setup if removing the module breaks nothing. The deletion
check is language-agnostic and also catches modules no test covers.

**L11. Percentages on ten samples.** Found: tenet dry run split 25 probes into 16/9; one probe moved
held-out fidelity 11 points, so the "2-point regression" rule fired on noise. Fix: held-out split is
exactly 40% per module by hash order; regression means two or more held-out probes lost; the report
shows agree/n and a 95% Wilson lower bound.

**L12. Answerer isolation was trust-based.** Found: designing the grading of the tenet dry run. Fix:
`score_probes.py` flags answers that contain a distinctive literal (quoted string, 3+ digit number,
snake/camel identifier) shared with the code-derived reference but absent from the spec snapshot; three
or more in one module fail the round for that module. Rebuild copies get spec text only, never
probes or answers.

**L13. Batch size was a guess.** Found: LiteLLM iteration 1 dispatch; the harness caps concurrent
subagents at 20 and rejected the 21st-24th launches. Fix: SKILL.md states the cap, keeps a dispatch
queue in `_meta/queue.txt`, launches up to cap minus two, and refills on each completion. Probers are
code-only, so they queue right behind extractors instead of waiting for reconciliation (halves wall
time for the probe phase).

**L14. Briefs that name files a partial run lacks.** Found: tenet answerer dry run; the brief told it
to start from INDEX.md and the cross-cutting files, none of which existed. It coped, but a less
careful worker could stall or invent. Fix: the answerer brief lists the snapshot and reads whichever
of those files exist.
