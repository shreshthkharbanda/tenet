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

**L15. The leak detector cried wolf on templates.** Found: grading the tenet dry round; 8 of 25
answers were flagged as leaks because they instantiated the spec's output template with values the
question supplied ("analyzed 3 files · 4 types"). Fix: suspicion is token-level; a literal counts only
if it carries a distinctive token (5+ letters or 3+ digits) found in neither the spec snapshot nor the
question. The planted-leak regression case still fires. A detector that fires on honest work trains
the orchestrator to ignore it, which is worse than no detector.

**L16. Judges saw defects the verdict could not express.** Found: tenet judge; three spec
inaccuracies (wrong cause for a right outcome, unstated quoting, colour span) did not flip any verdict
and lived only in prose. Fix: judgments carry an optional `spec_defect`; revision-split ones are
routed to the reviser as `defect_note` failures; held-out ones go only to the human report, because
feeding them to revisers would leak the held-out set.

**L17. Relative paths in worker reports.** Found: tenet extractor reported `specs/modules/report.md`
for a specs dir elsewhere; G5 resolved it against the repo and failed an honest worker. Fix: reports
use absolute paths; the verifier also tries the specs dir and its parent before failing.

**L18. Measurement contaminated by its own reports.** Found: regression-testing L15; the planted leak
stopped firing because the "spec corpus" included `_meta/validation-report.md` from the previous
round, which quoted the leaked literal. Fix: the corpus is spec text only (no `_meta`, no briefs).
General rule for every check: never let a measurement's own output feed its next input.

**L19. Identifiers swallowed as refs.** Found: the new self-test. The claim grammar treated every
leading backticked span as a ref, so "`add` returns ..." or "`Router.completion` retries ..." failed
lint with "path not found", pushing writers to reword claims around the parser. Fix: a span is a ref
only if shaped like a location (a slash or a file extension, optional `:L1-L2` or `::Symbol`); the
first span that is not ends the ref list. The change only relaxes the grammar, so workers already
mid-run are unaffected.

**L20. Gates had no tests of their own.** Found: L15, L18 and L19 were all gate bugs that real data
exposed; each would have silently mis-measured every later run. Fix: `scripts/selftest.py` builds a
fixture repo (with a specs dir deliberately not named `specs`) and asserts each gate's catches and
non-catches, one case per learning that changed a script. Run it after any script change; a change
that adds a learning adds a case.

## Iteration 1 (LiteLLM router subsystem: 10 modules, 23k LOC)

**L21. A restart erased the batch.** Found: the container restarted 20 workers into LiteLLM
extraction and probing. Every worker held its output in memory until the end, so nothing was on disk,
and the orchestrator's only record of the agent ids was its own context. Agents can be resumed from
transcripts, but only by id. Fix: every brief has a Durability clause (write the output file early,
save after each section, append probes/answers/verdicts as they are final, check the file first when
resumed); `dispatch.py` keeps a durable launch log with agent ids, a `running` listing to resume after
a restart, and a `next` listing that respects the concurrency cap.

**L22. Validation only from inside the method.** Found: planning the iteration-1 grading. Every gate
compares workers who share one method and one model: a lenient judge, a probe set answerable from
prior knowledge (LiteLLM is famous), or a spec that is precise about trivia and silent about what
matters would all pass. Fix: Phase 7 adversarial audit, built into the skill: falsifiers on a fixed
random claim sample (`sample_claims.py`), omission hunters who list the top behaviors before reading
the spec, a no-spec control answered as round 0 so every validation row shows lift over prior
knowledge, a blind judge audit oversampling "agree", a reader-then-checker teachability test, and a
red team on the gates. `score_audit.py` applies explicit pass thresholds.

**L23. Probers soften their own probes.** Found: LiteLLM failure-handling prober confirmed by
execution that `set_cooldown_deployments` writes the cooldown and then raises without a running loop,
then left it out as "too much of a gotcha". Self-censoring surprising behavior biases fidelity upward
on exactly the behaviors a reader most needs. Fix: the prober brief says gotchas, bugs, and sync/async
divergences make the best probes; probe what the code does, not what it should do.

**L24. Suspected defects had no home.** Found: LiteLLM iteration 1; probers and extractors found
likely bugs (`default_priority` makes every `acompletion` raise `TypeError`; a named credential may
survive a caller-redirected `api_base`; TPM counters read and written under different keys) and could
only mention them in prose replies the orchestrator might drop. A spec writer facing a bug either
"fixes" it in the spec (misleading the reviewer, failing a rebuild) or buries it. Fix: the rule is
specify what the code does, then flag it; module specs have an optional `## Suspected defects` section
of claims with the evidence; `collect_defects.py` builds `_meta/suspected-defects.md` from those
sections and from worker reports' `suspected_bugs`. Reviewing specs instead of code needs this list
most of all.

**L25. How to run the code was rediscovered per worker.** Found: LiteLLM iteration 1; probers found
the venv and executed every reference answer, while an extractor used the system interpreter, could
not import the package, and fell back to reading. The same environment knowledge was re-derived (or
not) by every worker. Fix: Phase 0 writes `_meta/env.md` (interpreter, env vars, test command,
baseline failures); `render_briefs.py` injects it as `{{RUN_ENV}}` into extractor, prober, reviser,
judge, and falsifier briefs. Phase 0 must also install the project's declared test environment
(extras and dependency groups) and confirm the scoped tests collect without import errors, not just
that some tests run.

**L26. Independent convergence was invisible.** Found: LiteLLM iteration 1; the deployment-limits
extractor and the data cross-cutting writer, isolated from each other, both flagged the same TPM
read/write key mismatch. Agreement between independent workers is the strongest evidence a suspected
defect is real, and nothing surfaced it. Fix: `collect_defects.py` counts, for each defect, the other
modules or roles that flagged overlapping lines, and ranks by it. The Reconciler harvests suspected
defects from gaps, implementation notes, and worker reports into each module's `## Suspected
defects`, so runs that predate the section (or workers that only mention a bug in prose) lose nothing.

**L27. Size-driven cuts split one responsibility across modules.** Found: LiteLLM router-deployments
extractor; the price-inheritance logic straddled the cut at line 9865, so it was half-specified by two
modules and marked inferred in both. `split_file.py` cut wherever size dictated, and the Surveyor
could only merge ranges, never move a cut. Fix: `split_file.py` considers every boundary between 70%
and 100% of the size cap and picks the most cohesive one (fewest calls crossing between the three
definitions on each side, least shared name prefix); it also prints all boundaries. The Surveyor may
move any cut to another boundary to keep one responsibility together, and G1 rejects a range that
starts anywhere but a definition boundary.

**L28. The rules changed under running workers.** Found: LiteLLM router-selection extractor noticed
`templates.md` change on disk mid-run (this loop edits the skill while workers run, as will anyone
improving it between phases). Workers in one run could follow different rules. Fix: `render_briefs.py`
copies the references workers read into `_meta/skill-refs/` on first render and briefs point there;
`--refresh-refs` re-copies deliberately. Scripts stay live, because gate fixes are meant to apply.

**L29. Coverage counted closures as public surface.** Found: LiteLLM coverage gate flagged
router-calls (65%) and router-dispatch (79%); every "missing" symbol was a wrapper class or closure
defined inside a method. A second bug hid behind the first: the nesting tracker popped a method at
the `) -> T:` line closing its multi-line signature, so everything inside looked class-level. Fix:
public symbols are definitions whose every enclosing block is a class; lines starting with `)` or `]`
do not close blocks (`}` does). The same run shows the gate's real catch: request-targets omitted 17
reachable public methods, and only that module now fails. A gate that fires on noise gets ignored when
it fires on signal.

**L30. Gate failures went to fresh workers.** Found: LiteLLM coverage failure on request-targets. A
fresh extractor would re-read 1800 LOC to name 17 methods. Fix: SKILL.md says to send gate failures
to the worker that wrote the file (SendMessage to its agent id from `dispatch.py`), which still holds
the module in context; re-dispatch fresh only when that agent cannot be resumed.

**L31. A correct spec rewritten to satisfy a broken gate.** Found: the request-targets coverage
failure (L29, L30). The 17 "missing" methods were described all along as `PatternMatchRouter.add_pattern`
and the like; the symbol matcher refused any name preceded by `.`, so qualified mentions never
counted. The orchestrator (this loop) misread the gate as signal and sent the worker to fix the spec;
the worker found the real cause. Fix: qualified mentions (`Class.method`, `module.func`,
`Type::method`) count; self-test case added. Rule for the orchestrator: before sending a gate failure
to a worker, open two of the flagged items in the spec and confirm they are really absent. A gate
false positive that a worker "fixes" is worse than none: it bends correct specs toward the checker.

**L32. Ref notation drifted, and probe refs were never checked.** Found: LiteLLM probe sample; probers
wrote `path:L145-230` because the prober brief and grammar line showed `path:L1-L2` while examples used
bare numbers; lint would have rejected the `L` form in claims, and probe refs were never resolved at
all. Fix: one notation in every doc (`path:START-END`), an `L` prefix accepted everywhere refs are
parsed, and `score_probes.py --assign-splits` resolves every probe ref (file exists, lines in range)
before the held-out split is frozen. The control answerer's brief is rendered inside its own
directory, like answerer briefs inside their snapshot, so reading it does not break isolation.

**L33. Reconciliation by reading could not scale.** Found: LiteLLM iteration 1 reconcile; 13 spec
files and about 2,950 claims. Finding contradictions by reading is hopeless, and one Reconciler
checking pairs against code would need ~750k tokens. Measured: 4,039 cross-file claim pairs cite
overlapping lines, and 75 are near-duplicates (61 with differing values). Cross-cutting writers run in
parallel with module extractors, so they restate module facts that then drift on revision. Fix:
`find_overlaps.py` builds the worklist (near-duplicates with differing values first); pair judges work
disjoint slices in parallel and only record decisions (distinct, contradiction, duplicate,
unresolvable) with exact claim edits; `apply_claim_edits.py` is the single writer, rewriting claim
lines by ID, so parallel judges cannot race; duplicates collapse to one owning claim plus pointers;
the Reconciler then writes only the top layer.

**L34. Bug reports outside the bug channel.** Found: LiteLLM pair judge 00 reported a likely bug
(`ttl=RoutingArgs.ttl`, the enum member, passed where `.value` is expected) only in its reply; its
brief had no worker report and no defect field. L24 gave extractors a channel, but every role reads
code and any of them can trip over a bug. Fix: `suspected_bugs` is part of the worker report format
for every role, the pair-judge brief now writes a worker report, and the template says a reply does
not survive and a report does.

**L35. Parallel judges editing the same claim.** Found: LiteLLM pair judge 01 noticed that claims in
its slice were also edited by pair judge 00 (a claim appears in several overlap pairs), so the applier's
file order would decide which text survived; it copied 00's text where it could, and three claims
still had divergent edits. Fix: `apply_claim_edits.py` groups edits by claim, applies only claims with
one agreed edit, leaves conflicting claims untouched, writes `reconcile/conflicts.json`, and exits
non-zero; the orchestrator resolves each conflict by picking the variant whose pointer reaches the
owning claim directly (or sends both to one judge). It also flags pointer chains (a pointer to a
pointer), which make a reader hop twice.

**L36. Cross-cutting files were second copies of the module specs.** Found: LiteLLM reconcile. Pair
judges found 78 of 120 "same-code" pairs were duplicates in paraphrase (my similarity classifier called
them distinct), and the new ownership gate measured restatement directly: 91% of 01-interfaces, 94% of
02-data, and 80% of 03-config claims restate behavior that module specs own, against 0-9% "foreign"
claims in module specs. Cross-cutting writers ran in parallel with extractors, could not cite claim IDs
that did not exist yet, and so re-specified everything; post-hoc dedupe of ~2,600 duplicate pairs is not
affordable, and every duplicate drifts on the next revision. Fix: Phase 2b runs cross-cutting writers
after module specs pass G2/G3; their brief makes them indexes (rows carry module claim IDs) that add
claims only for facts no module owns, and report module-claim problems instead of restating them;
`check_ownership.py` (G6, in `gate.py`) fails a cross-cutting file over 20% unpointed restatement and a
module spec over 10% claims about another module's lines. Probers move up beside extractors, since they
read only code.

**L37. Contradictions hide below the duplicate ranking, and the tail was assumed empty.** Found:
LiteLLM pair judges; the top 60 rows (near-duplicates with differing values) held 0 contradictions,
rows 60-300 held 8, the overlap list had 4,039 pairs and only the top 300 were judged. Fix:
`find_overlaps.py` appends a random sample of the unjudged tail (marked `tail_sample`), and
`apply_claim_edits.py` reports the tail's contradiction rate, telling the orchestrator to judge more
when it is 3% or higher. With L36 in place the list should shrink by an order of magnitude, which makes
judging all of it affordable.

**L38. Edits by line left stale sub-bullets, and tables carried untracked values.** Found: LiteLLM
pair judge 03; a claim it rewrote (RDEPLOY-003) had three sub-bullets the applier would have left in
place, and a config table still said "32768 nodes" after the claim it summarized was corrected. Fix:
`apply_claim_edits.py` replaces a claim's whole block (its line plus deeper-indented continuation
lines) and lists every table row that mentions an edited claim (`tables_to_review`, 119 rows in this
run) for the Reconciler; lint warns on table rows that state values but cite no claim ID, since nothing
can keep such a row in sync.

**L39. A directory-shaped identifier read as a ref.** Found: lint after applying LiteLLM edits; a
claim text starting with `os.environ/` parsed as a directory ref and failed resolution. Fix: a
directory ref needs two or more path segments; single tokens ending in `/` stay text. Self-test case
added beside L19's.

**L40. A wrong reference answer mis-scores every round.** Found: LiteLLM round-0 control judge
executed RDISP-P12 and showed its reference omitted a suffix appended under a default-on flag. Left
alone, the probe is "invalid" forever, shrinking the held-out set or penalizing a correct spec. Fix:
`correct_probe.py` amends the reference once (never the question or split), logged with reason and
evidence in `_meta/probe-corrections.jsonl`, so held-out integrity stays auditable. Judges that mark
probe_invalid with execution evidence feed it; the orchestrator applies corrections before the next
round.

**L41. A false PASS from a gate that skipped what it could not parse.** Found: LiteLLM iteration 1.
Every prober (and the control judges) hand-wrote its report in an invented schema with no `role`
field, so `verify_reports.py` never ran the prober-blindness check and reported "0 discrepancies":
G5 passed while verifying nothing. It later crashed outright on a report whose outputs were strings.
(Checked by hand afterwards: no prober read spec text; the method held, the gate did not.) Fix:
`write_report.py` is the only way workers write reports (every brief ends with the exact command, which
overrides older wording); `verify_reports.py` fails any report missing role, module, outputs, or
files_read, and treats malformed entries as findings rather than crashing. General rule for gates: a
check that cannot find its input must fail loudly, never skip silently.

**L42. Relayed suspicions are not findings.** Found: the `RoutingArgs.ttl` "bug" a pair judge
mentioned in passing and the orchestrator recorded was a false positive (the module defines its own
`RoutingArgs` with `ttl = 60`); the Reconciler disproved it. Fix: `--bug` entries carry how the worker
knows (read, executed, test), the Reconciler verifies every collected defect against code before it
becomes a claim, and suspected defects in the final report are only those that exist as claims.

**L43. A denylist snapshot leaked every new metadata file.** Found: building the LiteLLM round-1
answerer snapshot; `probe-corrections.jsonl` (a corrected reference answer) and the pair judges'
decision files (code-derived evidence not in the spec) were copied in, because the snapshot excluded
known-bad names and these were new. Caught before any answerer ran. Fix: the snapshot is an allowlist
(INDEX.md, 0*.md, modules/*.md, _meta/modules.json, question files); a self-test plants a correction and
a decision file and asserts neither reaches the snapshot. Rule: isolation boundaries are allowlists.

**L44. The Rebuilder could read the tests it is scored by.** Found: preparing the LiteLLM rebuild;
the rebuild copy keeps the tests (they are the scorer), and the brief only asked the Rebuilder not to
read them. A rebuilder that reads test source can satisfy assertions the spec never stated, and the
recovery rate would credit the spec. Fix: rebuilders report their copy with `--snapshot`, and
`verify_reports.py` fails a rebuilder that read outside its copy (the original is reachable on disk) or
read any test file inside it. Test failure messages seen while running stay fair game and are recorded
as spec gaps.

**L45. Hyphenated briefs never loaded.** Found: rendering the LiteLLM lifecycle checker; the brief
marker pattern used `\w+`, so `judge-auditor` and `lifecycle-checker` were silently absent from the
renderer, and the self-test only rendered roles it already knew. Fix: markers match `[\w-]+`; the
self-test now discovers every `<!-- brief:... -->` marker in the docs and renders each one.

**L46. Answerers saw spec ambiguity that verdicts could not express.** Found: LiteLLM round-1
answerers; many "agree" answers carried notes like "the spec does not say how placeholders render" or
"RSETUP-172 conflicts with RDISP-237". Those are spec defects whatever the verdict. Fix:
`score_probes.py` routes revision-split answers whose note reports silence, ambiguity, or contradiction
to the reviser as `answer_note` failures; held-out notes stay out, as with judge side notes (L16).

**L47. Message templates with unrendered placeholders.** Found: nearly every LiteLLM round-1
answerer marked answers partial because templates like `Valid options: [<names>]` or `Try again in
<X> seconds` never say whether a list is a repr or a join, whether 60 prints as `60` or `60.0`, or which
value fills the slot. A caller that matches on error text needs the exact string. Fix: the precision
ladder requires each placeholder's rendering or one fully rendered example; lint warns on backticked
literals containing `<...>` without either (200 warnings on the iteration-1 specs, routed to revisers).

**L48. Universal claims overreach.** Found: LiteLLM falsifiers. Of 36 sampled claims, universal
ones (always, never, unless, only, "takes effect", "is not retried") were falsified or imprecise 7 of
24 times (29%), others 1 of 12 (8%): "never retries a failed cache read" (a caller re-reads),
"update_settings takes effect on the next selection" (keys outside an allowlist are dropped), "returns
the deployment directly unless blocked" (an override selector's pre-call check still runs). Writers
check the paths they read and generalize; "absence of a safeguard is a behavior" invites exactly these.
Fix: universal claims are confirmed only when every covered path was traced, else scoped or inferred
(templates.md); `sample_claims.py` draws two thirds of confirmed picks from universal claims and has
`--universal-only`; Phase 5 starts with a universal-claim falsification pass per module whose findings
join the reviser's failures.

**L49. A test-verified reference that tested the wrong thing.** Found: LiteLLM deployment-limits
round-1 judge executed LIMITS-P25 through `Router.acompletion` and showed the reference wrong, and the
truth a security bug: a forged reservation is refunded because the refund runs before the forged keys
are stripped. The prober had "verified by test" with a unit test of the stripping helper. Fix: the
prober brief requires execution through the public entry point the question names; a test verifies a
reference only if it drives that entry point. The probe was corrected on the record (L40).

**L50. Caller relationships asserted from names.** Found: LiteLLM request-targets falsifier;
TARGETS-088 said the Router calls `resolve_served_model`; a search shows only two proxy budget checks
do, and the Router uses a different, similarly named method. The module also had the most failures of
any audited module (7 of 12 claims false or imprecise). Fix: the extractor brief requires caller claims
to cite the call sites found by search, and treats "no production caller" as a universal claim with a
stated scope.

**L51. Mechanisms stated per path, consequences never contrasted.** Found: LiteLLM router-calls
omission hunter; the spec said the concurrency slot is held "for the life of a chat stream" and
"around the provider call" for other wrappers, both true, without saying that open Responses/Messages
streams are therefore uncapped (filed as a suspected bug). Fix: implicit-decisions gains a Sibling
paths section: when one mechanism differs across sibling entry points, state the difference side by
side with its consequence for a caller.

**L52. Audit thresholds tied to a label nobody used; in-progress output scored as failure.** Found:
first LiteLLM audit score. Falsification passed because it counted only "high" severity, which no
falsifier assigned, while 24 of 60 sampled claims (40%) were false or imprecise and 10 of those medium
severity; and omission hunters still mid-run (behaviors listed, not yet graded) scored "0 stated".
Fix: falsification is judged in aggregate over audited modules (12 samples per module is too few) on
false <= 5%, medium-or-worse <= 10%, and zero high; ungraded omission rows read as pending.

**L53. The rebuilder's own brief tripped its isolation check.** Found: scoring the LiteLLM rebuild
(454/454 baseline tests recovered from the spec alone); the verifier flagged the brief path outside the
rebuild copy. Fix: rebuilder briefs render into `<scratch>/rebuild-<module>/_brief.md`, as answer and
control briefs render inside their snapshots.

**L54. The orchestrator forgot to log launches.** Found: LiteLLM iteration 1; three omission-hunter
launches never made it into `dispatch.jsonl`, so after a restart they would have been lost. A record
the orchestrator must remember to keep fails in the same moments it is needed. Fix: `dispatch.py
unfinished` needs no log: every rendered brief whose worker report (or, for pair judges, decision file)
does not exist is unfinished. The launch log stays as the way to resume by agent id; the unfinished
check is the ground truth for what is left.

**L55. Parallel revisers raced on shared files; two audit briefs ran blind to the environment.** Found:
LiteLLM round-1 revision setup. The failure-handling worklist held a contradiction between its own
module and `03-config.md` (CFG-123 vs IF-375 on `max_fallbacks`); ten revisers editing the shared
cross-cutting files in parallel would have overwritten one another, the same race L35 fixed for pair
judges. Separately, omission hunters and the lifecycle checker had no `{{RUN_ENV}}`, so they could not
run the declared test command to confirm a behaviour. Fix: a reviser edits only its own module file;
any fix to a shared file goes into `decisions-revise-<module>-round-<n>.jsonl` rows that the
single-writer `apply_claim_edits.py` applies after all revisers finish. Every brief that may execute
code now receives `{{RUN_ENV}}`.

**L56. Pointers were trusted by shape, not by target.** Found: preparing the LiteLLM cross-cutting
rewrite. Three related holes: (a) the ownership gate accepted any `[ID]` in a claim as a hand-off, so
46 cross-cutting claims passed G6 by pointing at another cross-cutting claim or an unrelated module;
(b) `lint_specs.py --only` downgraded an unresolved pointer to a warning, so a worker linting its own
file could leave pointers dangling; (c) regenerating a cross-cutting file from scratch would drop claim
IDs that module files and answers point to. Fix: G6 counts a pointer only when it names a claim of a
module that owns the cited lines; cross-references from the linted files resolve against every spec
file even under `--only`; a cross-cutting rewrite converts the file in place and never deletes or
renumbers an ID (a superseded claim becomes a pointer that keeps its ID and refs). The blind judge
audit in the same round (37/40 reproduced, no leniency) added one checklist item: a validation
library's exact error text and coercions (pydantic turning `12` into `12.0` in a timeout message) are
caller-visible behavior; run the validator once and copy the text.

**L57. The score trusted its inputs, and the answer key sat beside the writers.** Found: LiteLLM red
team, round 1: a gutted spec set with empty answers judged "agree" passed every gate and was stamped
validated. The integrity holes, by class:
(a) Held-out reference answers, judgments and leak literals lived under `$SPECS/_meta`, one recursive
grep from every writer. Fix: they live in `$EVAL`, outside the specs dir and the repo (inventory
refuses otherwise); writers are never told its path; the specs dir gets a table-only summary.
(b) G4 scored verdicts as given. Fix: agree on an empty or unanswerable answer is an error; 3+ agrees
sharing none of the reference's literals is an error (real runs: at most 2 per module); a held-out
`probe_invalid` counts as a miss until corrected; validated needs at least 8 valid held-out probes;
70%+ answers copying reference 6-grams absent from the spec is an error.
(c) G5 checked what workers said they read. Fix: with `--transcripts`, G5 parses each worker's tool
calls (Read/Grep/Glob paths, Bash paths after expanding variables set in the command, file paths
printed by searches) and applies role rules to those; reports are reconciled with the dispatch log by
brief (a relabelled or missing report fails); outputs must postdate the launch; claim counts and
hashes are computed by write_report, not stated. Spec text is recognized by frontmatter wherever it
lives. On the LiteLLM run this confirmed that no round-1 reviser touched held-out material; it also
caught the reconciler brief sending the reconciler to `validation.json` (fixed in the brief; waived
on evidence: the file did not exist then). Waivers need a reason and evidence and print every run.
(d) Gates skipped silently (`--round` with no probes; zero reports) and `apply_status` stamped
validated over a failed gate. Fix: both fail; apply_status reads status.json and lenient/leak counts.
(e) `correct_probe.py --question-append` rewrote held-out questions untraced. Fix: old and new
question are logged, evidence must cite code that resolves, held-out edits need `--allow-holdout`.

**L58. Mechanical appliers replayed history.** Found: LiteLLM round-1 revision. `apply_claim_edits.py`
re-applied every decision file on each run, so applying the revisers' shared-file rows would have
re-applied the pair judges' old edits over claims revisers had since rewritten, and an old and a new
edit to one claim read as a conflict; one reviser left a wrong shared claim alone to avoid that
"conflict". `--dry-run` also wrote its summary files. `build_revise.py` appended rebuild rows again on
each run, so one reviser worked 68 rows of which 27 were repeats. Fix: a ledger (file -> sha256)
records applied decision files, which are never replayed, and a changed ledgered file is an error;
dry runs write nothing; build_revise dedupes on (source, id). Same round: rendering message templates
by running the code exposed wrong claims in 4 modules (the precision ladder is a falsification tool,
not just formatting).

**L59. Gates counted refs and pointers without checking what they point at.** Found: LiteLLM red team,
round 1 (exploits 4, 5, 8, 9, 11, 13): a module cut to 16 bare-path claims, or truncated after its
first third, passed lint and coverage; refs to `::None`, a directory or lines 1-2 passed; a
contradiction hid from reconciliation behind a ref wider than 120 lines or inside one file; G6 took
any owner-module pointer, related or not. Fix: G3 adds line coverage from the module's own refs of
<= 120 lines (>= 60%; real modules 78-93%, truncated 39%, hollow 0%), an anchor check (<= 15% of
claims whose backticked tokens are absent from the cited lines; real 3-11%), symbols matched in
visible text only, and cross-cutting refs no longer count toward a module; lint errors on repeated
claim text, unfalsifiable stock phrases in confirmed claims (0 real hits before adding each), `::Symbol`
refs that name no definition, and an unknown commit stamp; find_overlaps pairs same-file and
wide-ref claims; a G6 pointer must name a related claim (overlapping lines or a shared literal;
honest pointers kept 204/205). Every threshold was set from the false-positive rate measured on the
real specs before it was turned on.

**L60. Scratch harnesses outlived their round and shadowed packages.** Found: LiteLLM round-2
falsifier; a round-1 `h2.py` left in the shared scratch dir shadowed the real `h2` HTTP/2 package when
the proxy was imported. Fix: every run environment handed to a worker ends with a hygiene line: a new
subdirectory per task, scripts named `check_<id>.py`, run with `python -P`.

**L61. Revision does not move the spec-wide error rate; execution does.** Found: LiteLLM round 2. A
fresh falsification sample after a full revision round found 10% of claims false and 21% wrong at
medium+ severity (round 1: 7% and 17%), spread evenly: universal 41% false-or-imprecise, plain 39%;
{confirmed} 35%, {inferred} 59%. Revision fixes what a probe or audit happened to touch, about 3% of
claims per round. The wrong claims share one shape: they state what code outside the cited lines does
(what the provider call receives after a "sanitizing" helper, how a dependency logs, what a sync
sibling path does, whether a dict is copied). Falsifiers find them by driving the public entry point;
writers state them from reading. Fix: G7 executable evidence. A verifier role backs each {confirmed}
normative claim with `_meta/evidence/<module>/check_<ID>.py` (drives the entry point, asserts the
observables, records the claim text it verified) or a pinning test, and corrects the claim through a
decision row when the check disagrees; `check_evidence.py` re-runs every check, flags stale ones (claim
text changed) and orphans, and reports an evidence rate. Re-running the evidence after a code change
lists exactly the claims that went stale. Also: notes of the form "module claim X-NNN: problem" in any
worker report now reach the owner's revise worklist (they were read by no one), out-of-sample falsifier
findings are fixed without being counted, and one-time findings (rebuild guesses, notes) are never
handed to a second round (27 already-fixed rebuild rows came back).

**L62. Run environment missing from writers that verify.** Found: LiteLLM cross-cutting conversion;
the config writer could not import the project (system Python, no `openai`) and settled facts by
reading, because its brief had no `{{RUN_ENV}}` (L55 fixed only the briefs found then). Fix: crosscut,
reconciler and surveyor briefs get it, and a selftest asserts every executing role has it while the
spec-only roles (answerer, control, rebuilder) never do.

**L63. Moving outputs after the fact broke the audit trail.** Found: LiteLLM round 2. Archiving the
round-1 audit outputs by hand broke five omission reports' paths (G5 failed), and round-2 falsifier
reports overwrote round-1's because report names carried no round. Fix: every audit role is rendered
and reported with `--round N` and writes under `_meta/audit/round-N/` (`$EVAL/audit/round-N/` for the
judge audit); one shared brief-to-report mapping (`_common.expected_report`) serves dispatch and G5;
never move a worker's outputs by hand.

**L64. Judges anchored on the previous round's verdicts.** Found: LiteLLM round 2; a judge read the
round-1 judgments "to keep verdicts consistent" and carried two lenient calls forward. Each round's
fidelity is only a measurement if its verdicts are independent. Fix: the judge brief forbids reading
other rounds' judgments and answers, and G5 flags a judge whose transcript touches them. The affected
round-2 judgments are re-run rather than waived.

**L65. Checks inherited the system's own shared-state bug.** Found: LiteLLM G7 run; AFFINITY-180's
check built a second "fresh pod" Router in the same process, and LiteLLM's process-global callback list
keeps one instance per class, so the second router silently used the first router's cache, and the
check's verdict also depended on which concurrent write landed last. It passed for its author and failed
under the gate's parallel load. Three verifiers independently hit the same leak. Fix: the run-environment
hygiene line tells every executing worker to build one instance of the system per check process and
never to assert timing-dependent order; failing and stale evidence checks go to the owner's revise
worklist (source "evidence") to fix the claim or the check; G7 runs checks in parallel, each in its own
working directory, with one serial re-run that separates a flaky check from a wrong claim.

**L66. Executable evidence removes false claims; omissions survive it.** Found: LiteLLM evidence
experiment. Twelve verifiers backed 274 confirmed normative claims of two modules with check scripts
and corrected 73 (26%), finding several real LiteLLM bugs no reading pass had caught (a caller-forged
reservation decrements another deployment's rate-limit counter; router I/O reservations are never
reconciled; a second Router in one process silently shares the first's pre-call checks). A blind
falsification sample afterwards (12 fresh confirmed normative claims per module, same seed rules):
verified modules 0/24 false, 25% false-or-imprecise, 12% medium+, 0 high; unverified controls 3/24 false
(12%), 38%, 17%, 1 high. What survived verification is omission: claims true as stated that leave out
a condition a caller would hit (the store down, an unparseable value, a stream closed before its first
read, a second instance). Fix: the evidence sweep is Phase 3b of the pipeline; the verifier brief now
attacks those unstated conditions after checking the stated ones; revisers update a claim's check when
they change the claim; revise worklists collect findings from every audit round, keyed by the round
that found them (a claim found wrong again later is a new finding).

**L67. Revisers executed claims and threw the scripts away.** Found: LiteLLM round-2 revision; every
reviser confirmed its rewrites by running check scripts in its own scratch dir, so the run produced
dozens of verified checks that the gate never saw again. Fix: the reviser brief tells them to save each
such script as the claim's evidence check (`_meta/evidence/<module>/check_<ID>.py` with the `# claim:`
and `# text:` headers), so G7 coverage grows with every revision at no extra cost.

**L68. A reviser's shared-file row reached into another module.** Found: LiteLLM round-2 revision;
the request-targets reviser wrote a decision row rewriting RCALL-065, a router-calls claim, while the
router-calls reviser was rewriting its own module in parallel: the single-writer applier would have
overwritten the owner's work after it finished. Fix: apply_claim_edits applies a reviser's rows only to
shared files (and its own module); a row against another module's spec is diverted to
`reconcile/diverted.jsonl`, and build_revise hands it to that module's next reviser as a note with
the proposed text and evidence.
