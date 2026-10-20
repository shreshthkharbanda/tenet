# Worker briefs

Each brief below is the complete instruction set for one subagent. Render it with
`scripts/render_briefs.py` (which fills every placeholder from modules.json, the shard report, and the
inventory), then launch the Agent with `subagent_type: general-purpose`, `run_in_background: true`, and
the prompt "Your complete instructions are in <brief path>. Read that file first and follow it exactly." A worker has
only this text: it did not see the conversation, the research, or the other workers. That is deliberate.
Independence is what makes the validation honest (an answerer that saw the code is not measuring the
spec), so do not "helpfully" add context that breaks the isolation a brief sets up.

Placeholders used throughout: `{{REPO}}` absolute repo root, `{{SPECS}}` absolute specs dir,
`{{SKILL_DIR}}` absolute path of this skill, `{{COMMIT}}` HEAD sha, `{{MODULE_ID}}`, `{{PREFIX}}`,
`{{MODULE_NAME}}`, `{{GLOBS}}`, `{{FILES}}` (explicit file list from `_meta/shards-report.json`),
`{{TEST_FILES}}`, `{{ROUND}}`, `{{N_PROBES}}`, `{{SCOPE_NOTE}}`, `{{SPEC_SNAPSHOT}}`, `{{SCRATCH}}`,
`{{TEST_CMD}}`. Do not fill these by hand: `scripts/render_briefs.py` renders each brief to a file and
refuses to write one with a placeholder left; the Agent prompt is then one line pointing at that file.

Contents: 1 Surveyor · 2 Extractor · 3 Cross-cutting extractors · 4 Reconciler · 5 Prober ·
6 Answerer · 7 Judge · 8 Reviser · 9 Rebuilder

---

## 1. Surveyor

<!-- brief:surveyor -->
```
You are surveying a codebase so it can be split into modules for specification. Read-only on the repo;
write only the two files named below.

Repo: {{REPO}} (commit {{COMMIT}}). Inventory: {{SPECS}}/_meta/inventory.json (files, LOC, languages,
tests, entry hints, build hints). Read it first. Only records with in_scope=true are yours to shard.
Scope: {{SCOPE_NOTE}}

Produce:
1. {{SPECS}}/_meta/modules.json
2. {{SPECS}}/_meta/survey.md

modules.json schema:
{
  "commit": "{{COMMIT}}",
  "modules": [
    {"id": "auth", "prefix": "AUTH", "name": "Authentication and sessions",
     "globs": ["src/auth/**"], "test_globs": ["tests/auth/**"],
     "depends_on": ["db"], "entry_points": ["src/auth/api.py::login"],
     "critical": true, "rebuild_candidate": true,
     "rationale": "one sentence on why these files form one responsibility"}
  ],
  "excluded": [{"glob": "examples/**", "reason": "fixtures used only by tests"}]
}

Rules the gate enforces (check_shards.py): every in-scope source file (kind=source, not test, not
generated, in_scope) matches exactly one module's globs or an excluded glob; ids are lowercase slugs;
prefixes are 2-12 uppercase alphanumerics, unique, and not IF/DATA/CFG/OPS/SYS; no module above 6000
LOC (one extractor must hold it in context) and preferably none under 150.

Files too large for one module are split into line ranges: a "globs" entry may be "path:START-END"
for one exact file. The ranges of a file must be contiguous, non-overlapping, and cover every line.
If the Scope above already lists cut points, use those. Otherwise get them from
`python3 {{SKILL_DIR}}/scripts/split_file.py {{REPO}} <path> --max-loc 3500` (cuts only at definition
boundaries); you may merge adjacent ranges, never cut elsewhere. A module may
mix ranges and whole files when they share a responsibility.

Check your plan before finishing:
  python3 {{SKILL_DIR}}/scripts/check_shards.py --inventory {{SPECS}}/_meta/inventory.json --modules {{SPECS}}/_meta/modules.json
and fix every error.

How to split well:
- Modules follow responsibility, not directory, but directories are the default when they already
  track responsibility. A module should be describable in one sentence.
- Read README, build files, and the entry-hint files to learn what the system is for and how it is
  invoked. Skim one or two files per candidate module; do not read everything.
- Mark `critical: true` for modules on the main paths (entry points, core domain logic, persistence,
  money or auth). Mark `rebuild_candidate: true` for modules that are pure enough to reimplement from a
  spec and have tests that can be run in isolation.
- Exclude vendored code, generated code, fixtures, examples, and scripts that are not product behavior,
  each with a reason. Do not exclude anything else.
- Large repos: aim for modules of 1500-5000 LOC; small repos: 300-1500.

survey.md (prose, 1-3 pages): what the system is; how it is invoked; the main paths at the level of
"request arrives at X, goes through Y, persists in Z"; external systems; data stores; configuration
surface; cross-cutting concerns you noticed (auth, retries, logging, errors); risks for specification
(huge files, metaprogramming, generated code, dynamic dispatch); a suggested reading order.

Finish by writing {{SPECS}}/_meta/worker-reports/surveyor-all.json per the format in
{{SKILL_DIR}}/references/templates.md section 7, then reply with: module count, total in-scope LOC,
modules over 6000 LOC (if any), and the three biggest risks.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

## 2. Extractor (one per module, fully parallel)

<!-- brief:extractor -->
```
You are writing the behavioral specification of one module of a codebase. Your output will be
validated mechanically (claim grammar, refs, coverage), then tested by having a separate reader answer
code-derived questions from your spec alone. Precision and completeness about observable behavior are
what count. Implementation detail is not.

Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}} ("{{MODULE_NAME}}"), prefix {{PREFIX}}.
Files in scope:
{{FILES}}
{{SCOPE_NOTE}}
Tests for this module:
{{TEST_FILES}}
Context: {{SPECS}}/_meta/survey.md (read it first for the system map).

Before writing, read all of:
- {{SKILL_DIR}}/references/templates.md (claim grammar, confidence rules, precision ladder, writing
  rules, and the modules/<id>.md template; copy the template's frontmatter and section headings exactly)
- {{SKILL_DIR}}/references/implicit-decisions.md (walk every item for this module)

Method:
1. Read the tests first; they pin behavior. A test file over ~2000 lines is not read whole: grep it for
   your public symbols and read the matching tests. Then read every in-scope file (or range)
   completely, in chunks if needed, and say in your report notes which parts you read in chunks.
   Public surface created at runtime counts: names bound by assignment from a factory, setattr loops,
   registration tables, decorators that wrap or rename, and attributes generated from data files. List
   every resulting public name in the Public surface table with a ref to where it is bound, because
   these names never appear as definitions and a reader cannot find them otherwise.
2. Grep for callers of each public symbol outside the module (what callers rely on is contract).
3. Open dependencies only as far as needed to state this module's behavior; what you did not trace is
   {inferred} or {gap}, never {confirmed}. Where reading leaves you unsure, execute: copy what you need
   to {{SCRATCH}}/extract-{{MODULE_ID}}/ and run a throwaway harness there (never in the repo). How to
   run this project's code here: {{RUN_ENV}}
   If behavior looks unintended, state what the code does in the normative sections anyway, and add it
   under "## Suspected defects" with the evidence (see templates.md).
4. Write {{SPECS}}/modules/{{MODULE_ID}}.md. Every fact is a claim with an ID {{PREFIX}}-001, -002, ...
   and a verified ref (path:L1-L2 relative to the repo root, or path::Symbol). Aim for one claim per
   10-30 lines of non-trivial logic; a 2000-LOC module typically needs 60-150 claims. Every in-scope
   file must be cited by at least one claim or named in Scope and boundaries as trivial/dead with a
   reason. Every public symbol should be named in the spec.
5. Walk implicit-decisions.md again and add the claims it surfaces, including explicit "no X" claims.
6. Re-read your spec as the blind reader: for each public entry point, could someone answer "what
   happens when the input is empty / too large / malformed / the dependency fails / the config is
   unset" from your text alone? If not, add the claim or the gap.

Hard rules: write only {{SPECS}}/modules/{{MODULE_ID}}.md and your worker report; do not modify any
source file; do not read other files under {{SPECS}}/modules/ (modules are specified independently and
reconciled later); never copy secrets (write [REDACTED] and a gap); do not mention tools or models;
no code transcription (short literals in backticks are fine).

Finish by running:
  python3 {{SKILL_DIR}}/scripts/lint_specs.py {{SPECS}} --repo {{REPO}} --only modules/{{MODULE_ID}}.md
and fixing every error it reports (other workers are writing other files in parallel; --only keeps
the lint to yours). Then write
{{SPECS}}/_meta/worker-reports/extractor-{{MODULE_ID}}.json (format: templates.md section 7) with an
accurate claim count and the full list of files you read. Reply with: claim counts by confidence, files
you could not cite and why, and the three behaviors you are least sure about.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

## 3. Cross-cutting extractors (four, parallel with module extractors)

One template, four focus blocks. `render_briefs.py --role crosscut --kind <interfaces|data|config|operations>`
fills `{{XC_*}}` from the focus block below.

<!-- brief:crosscut -->
```
You are writing one cross-cutting file of a behavioral specification of a codebase: the {{XC_KIND}}
file. Module specs are being written in parallel by others; yours is the system-wide view of one
concern. Precision about observable behavior counts; implementation detail does not.

Repo: {{REPO}} (commit {{COMMIT}}). Output: {{SPECS}}/{{XC_FILE}} (frontmatter kind: {{XC_KIND}},
prefix: {{XC_PREFIX}}). Scope: {{SCOPE_NOTE}}
Module map: {{SPECS}}/_meta/modules.json. System survey: {{SPECS}}/_meta/survey.md (read first).

Focus:
{{XC_FOCUS}}

Before writing, read {{SKILL_DIR}}/references/templates.md (grammar, confidence, precision ladder,
writing rules, and the template for {{XC_FILE}}; copy its frontmatter and headings exactly) and
{{SKILL_DIR}}/references/implicit-decisions.md.

Every fact is a claim {{XC_PREFIX}}-001, -002, ... with a verified ref (path:L1-L2 or path::Symbol,
relative to the repo root). You may read any source in the repo. Do not read {{SPECS}}/modules/
(those are being written independently). Do not modify source. No tool or model mentions. Redact
secrets as [REDACTED] plus a gap.

Finish by running:
  python3 {{SKILL_DIR}}/scripts/lint_specs.py {{SPECS}} --repo {{REPO}} --only {{XC_FILE}}
and fixing every error. Write {{SPECS}}/_meta/worker-reports/{{XC_KIND}}-all.json (format:
templates.md section 7) with an accurate claim count and every file you read. Reply with claim counts
by confidence and the three facts you are least sure about.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

<!-- focus:interfaces -->
```
Enumerate every external entry point in scope: CLI commands and flags, HTTP routes with methods,
public library API (exported classes, functions, constructor parameters), events consumed and
produced, scheduled jobs, signals, exit codes. For each: inputs with types and constraints, outputs,
errors, auth, idempotency. Then the error catalog: every error type, code, and exact message a caller
can see. Start from the entry hints in _meta/inventory.json, routers, CLI parsers, exported symbols,
and README usage. This file is the interface lock a rebuilder must honor, so exact names, parameter
names, defaults, and literals matter most here.
```

<!-- focus:data -->
```
Every durable store, schema, migration, file format, serialization format, cache, and the invariants
on them, plus in-memory state whose lifetime outlives one call (caches, cooldown tables, counters).
Start from migrations, ORM models, schema files, serializers, cache clients, and anything that opens a
file or socket for writing.
```

<!-- focus:config -->
```
Every environment variable, constructor or function parameter that acts as a tunable, flag,
config-file key, module-level constant used as a limit or timeout, and feature flag: type, default,
where read (import time, construction, per call), precedence among sources, and behavior when invalid
or missing. Grep for os.environ, getenv, System.getenv, process.env, config loaders, flag parsers,
settings objects, and constants named like limits, timeouts, retries, or TTLs.
```

<!-- focus:operations -->
```
Build, test, run, deploy, CI, observability (logs, metrics, traces that carry data, with formats),
and load-bearing third-party dependencies with versions and why they matter. Start from build files,
CI config, Dockerfiles, Makefiles, and the build hints in _meta/inventory.json. Include the exact
command that runs the tests for the scope and whether it passed when you tried it.
```

## 4. Reconciler (one, after all extractors pass lint and coverage)

<!-- brief:reconciler -->
```
You are reconciling independently written module specifications into one coherent specification set
and writing its top layer. Read everything under {{SPECS}} except _meta/probes, _meta/answers,
_meta/judgments. Repo: {{REPO}} (commit {{COMMIT}}). Survey: {{SPECS}}/_meta/survey.md.
Scope of the specification: {{SCOPE_NOTE}}

Tasks, in order:
1. Contradictions. Where two specs state the same fact with different values (a retry count, a
   default, an error code, an ordering), open the code at both refs and fix the wrong one in place
   (edit the claim text; keep its ID). If the code itself is inconsistent or you cannot decide, leave
   both and record the pair in {{SPECS}}/_meta/questions.md with both claim IDs and refs.
2. Cross-links. Where a module spec says "see module X" or describes a dependency's behavior, add the
   concrete claim ID cross-reference `[X-NNN]` so a reader can jump. Do not duplicate claims across
   modules; one fact lives in the module that decides it, and other modules point at it.
3. Write {{SPECS}}/00-overview.md per the template in {{SKILL_DIR}}/references/templates.md: purpose,
   system map table, 3-7 main paths as ordered steps citing claim IDs end to end, global invariants as
   SYS claims with refs, cross-cutting concerns, glossary, reading order. Write for an engineer new to
   the codebase who has 15 minutes; this is the short book the module specs are appendices to.
4. Write {{SPECS}}/_meta/gaps.md: every {gap} claim in every spec, grouped by module, with ref and
   question, plus what would resolve it (a test to write, a person to ask, a dependency to read).
5. Write {{SPECS}}/INDEX.md per the template (under 100 lines). Leave fidelity and rebuild columns
   as "pending" if _meta/validation.json does not exist yet; the orchestrator refreshes the table later.

Rules: edits to module specs are limited to fixing contradicted values, adding cross-references, and
fixing lint errors. Never renumber or reuse claim IDs. Never remove a {gap} because it is
inconvenient. Do not read source beyond what resolving a contradiction needs. No tool or model
mentions anywhere.

Finish by running `python3 {{SKILL_DIR}}/scripts/lint_specs.py {{SPECS}} --repo {{REPO}}` until it
passes, write {{SPECS}}/_meta/worker-reports/reconciler-all.json, and reply with: contradictions
fixed, contradictions left as questions, cross-links added, and the main paths you documented.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

## 5. Prober (one per module, parallel; code-only, never sees the spec)

<!-- brief:prober -->
```
You are writing fidelity probes for one module of a codebase: questions about its observable
behavior whose correct answers come from the code. Another reader will later try to answer them from
a written specification they have, without seeing the code. Agreement measures whether the spec
captured the code. You must NOT read anything under {{SPECS}} except _meta/modules.json and
_meta/survey.md; if you read the spec, the measurement is void.

Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}} ("{{MODULE_NAME}}"), prefix {{PREFIX}}.
Files in scope:
{{FILES}}
Tests:
{{TEST_FILES}}

Write {{N_PROBES}} probes to {{SPECS}}/_meta/probes/{{MODULE_ID}}.jsonl, one JSON object per line:
{"id": "{{PREFIX}}-P01", "module": "{{MODULE_ID}}", "category": "validation|error|branch|side_effect|config|interface|data|concurrency|default",
 "edge": true, "question": "...", "reference_answer": "...", "refs": ["path:L1-L2"],
 "difficulty": "easy|medium|hard", "verified_by": "reading|execution|test"}
`edge` is true when the probe exercises an error or boundary path (empty, missing, oversized,
malformed, dependency failure, timeout, null). `verified_by` says how you confirmed the reference.

Observability rule: ask only about behavior a caller, a user, a downstream system, or a stored record
could observe: return values, raised errors and their exact types/codes/messages, validation outcomes
and their order, persisted changes, external calls, log lines that carry data, config-dependent
branching, ordering and concurrency guarantees, defaults. Never ask about private names, internal call
structure, or code style.

Mix: at least 30% on error and edge paths (empty, missing, oversized, malformed, dependency failure,
timeout), at least 20% on validation rules and their ordering, at least 15% on configuration and
defaults, the rest on main-path behavior, side effects, data, interfaces. Cover every public entry
point with at least one probe. Prefer questions with a single checkable answer ("What status code and
message are returned when X?") over open ones. Do not filter out behaviors because they look like
gotchas, bugs, or accidents of implementation: a surprising-but-reachable behavior (a write that
happens before a raise, a setting silently ignored, sync and async paths that differ) is exactly what
a spec omits and a caller trips over, so it makes the best probe. Probe what the code does, not what
it should do. Reference answers must be exact and cite the lines
that prove them; a reference answer you cannot cite is not a probe, drop it.

Read the tests: behaviors pinned by tests make the best probes, and tests often reveal edge cases.
Where it is cheap, confirm reference answers by executing the code: copy what you need into
{{SCRATCH}}/probe-harness-{{MODULE_ID}}/ and run a throwaway harness there (never in the repo).
How to run this project's code here: {{RUN_ENV}} An
executed reference answer beats a read one; mark it verified_by: execution.

Do not read other modules' probes. Do not modify any file outside _meta/probes/. Write
{{SPECS}}/_meta/worker-reports/prober-{{MODULE_ID}}.json listing every file you read. Reply with the
probe count by category and difficulty.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

## 6. Answerer (one per module per round; spec-only, never sees the code)

<!-- brief:answerer -->
```
You are answering questions about a software system using ONLY its written specification. This is a
measurement of the specification, not of you: if the spec does not say, the right answer is
"unanswerable". Guessing from general knowledge or from what a system like this usually does corrupts
the measurement and will be detected.

Your only readable inputs are the files under {{SPEC_SNAPSHOT}} (a copy of the specs). Do not open
any file outside that directory. Do not run the code. Do not use git. If you find yourself wanting to
look at source to be sure, stop and mark the probe unanswerable.

Questions: {{SPEC_SNAPSHOT}}/_meta/probes/{{MODULE_ID}}.questions.jsonl (fields: id, question; no
reference answers are included on purpose).

Start with {{SPEC_SNAPSHOT}}/INDEX.md (if present) and {{SPEC_SNAPSHOT}}/modules/{{MODULE_ID}}.md,
then follow cross-references into whichever of 00-overview.md, 01-interfaces.md, 02-data.md,
03-config.md and other module specs exist in the snapshot. List the directory first; a partial run may
not have all of them, and a missing file is not an error.

Write {{SPECS}}/_meta/answers/round-{{ROUND}}/{{MODULE_ID}}.jsonl, one object per question, same
order:
{"id": "...", "answer": "exact answer, quoting literals from the spec", "unanswerable": false,
 "claims_used": ["{{PREFIX}}-012", "CFG-004"], "note": "optional: where the spec was ambiguous"}

For an unanswerable probe set "unanswerable": true, answer "", and say in note what the spec would
need to say. For a partially answerable probe, answer what the spec supports and say what is missing.

Write {{SPECS}}/_meta/worker-reports/answerer-{{MODULE_ID}}-round-{{ROUND}}.json with
"snapshot": "{{SPEC_SNAPSHOT}}" and every file you read in files_read (all must be under
{{SPEC_SNAPSHOT}}; this brief itself is there too). Reply with: answered, partial, unanswerable counts.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

## 7. Judge (one per module per round)

<!-- brief:judge -->
```
You are judging whether answers derived from a specification agree with reference answers derived
from the code. Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}}.

Inputs:
- probes with reference answers and refs: {{SPECS}}/_meta/probes/{{MODULE_ID}}.jsonl
- spec-only answers: {{SPECS}}/_meta/answers/round-{{ROUND}}/{{MODULE_ID}}.jsonl

For each probe, decide one verdict:
- agree: the answer states the same observable behavior as the reference (wording may differ;
  literals, codes, orderings, and conditions must match).
- contradict: the answer asserts a different behavior than the reference. This is a spec bug.
- gap: the answer is unanswerable or so partial that the distinguishing fact is missing. This is a
  spec omission.
- probe_invalid: the reference answer is wrong or the question is unobservable or ambiguous. Verify by
  opening the cited lines (and executing if needed: {{RUN_ENV}}); you may read source for this purpose
  only. Use sparingly and explain.

A spec that is more precise than the reference (gives the exact message where the reference gives the
code) still agrees. A spec that hedges ("usually", "may") where the code is deterministic does not
agree; mark gap and say the hedge is the defect.

Write {{SPECS}}/_meta/judgments/round-{{ROUND}}/{{MODULE_ID}}.jsonl:
{"id": "...", "verdict": "agree|contradict|gap|probe_invalid", "note": "one line: the distinguishing fact",
 "spec_defect": "optional: a spec inaccuracy you noticed that did not change the verdict"}
Record spec_defect whenever the spec states something the code contradicts or leaves out, even when
the answer still agrees (e.g. the right outcome attributed to the wrong cause). These are routed to
revisers mechanically; do not bury them in the note.

Do not read or edit any spec file; your job is comparison, not repair. Write
{{SPECS}}/_meta/worker-reports/judge-{{MODULE_ID}}-round-{{ROUND}}.json. Reply with the verdict counts.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

## 8. Reviser (Extractor in revise mode; one per failing module per round)

<!-- brief:reviser -->
```
You are revising the specification of one module after fidelity probing found contradictions and
gaps. Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}}, prefix {{PREFIX}}.
Spec to revise: {{SPECS}}/modules/{{MODULE_ID}}.md (also fix 01-interfaces.md / 02-data.md /
03-config.md if a failure's root cause lives there).
Failures: {{SPECS}}/_meta/revise/round-{{ROUND}}/{{MODULE_ID}}.jsonl (question, reference answer,
refs, the spec-only answer, verdict, judge note). These are the revision-split probes only; a separate
held-out set you will never see is scored afterwards, so fixing exactly these questions is not the
goal. Fixing what they reveal is.

Read {{SKILL_DIR}}/references/templates.md (grammar, rules) and
{{SKILL_DIR}}/references/implicit-decisions.md first.

For each failure:
1. Open the cited code and confirm the reference answer (execute it if unsure: {{RUN_ENV}}). If the
   reference is wrong, say so in your report notes and change nothing for it.
2. Classify the root cause: a wrong claim (contradiction), a missing claim (gap), a claim that exists
   but is too vague to answer from (hedging, missing literal), or a claim in the wrong file.
3. Fix the root cause, not the symptom: rewrite the wrong claim in place (same ID), add the missing
   claim with the next unused ID, replace hedges with exact behavior, add the ordered checks or the
   table the question needed. Then ask what sibling behaviors share the same cause (if the 404 message
   was missing, are the other error messages present?) and fix those too.
4. Do not touch claims unrelated to the failures. Edits elsewhere are how revisions regress.

Never renumber or reuse IDs. Never delete a {gap} unless you resolved it from code. Run
`python3 {{SKILL_DIR}}/scripts/lint_specs.py {{SPECS}} --repo {{REPO}} --only modules/{{MODULE_ID}}.md`
(add `--only 01-interfaces.md` etc. for any other file you edited) until clean. Write
{{SPECS}}/_meta/worker-reports/reviser-{{MODULE_ID}}-round-{{ROUND}}.json. Reply with: failures by
root-cause class, claims rewritten, claims added, references you judged wrong.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```

## 9. Rebuilder (optional round-trip; one per selected module)

<!-- brief:rebuilder -->
```
You are reimplementing one module of a software system from its written specification, to measure
whether the specification is sufficient. Work only inside {{SCRATCH}}, a copy of the repository
from which this module's code has been removed (whole files deleted, or line ranges replaced by a
line containing REBUILD-MARKER {{MODULE_ID}}). Tests are kept. The original implementation is not
available to you: do not use git, do not look for backups or other copies on disk, do not open
anything outside {{SCRATCH}}, do not search the internet for this project. If the spec is
insufficient, that is the finding; write what the spec supports and record every place you guessed.

Specs: {{SCRATCH}}/specs (INDEX.md, 00-overview.md, 01-interfaces.md, 02-data.md, 03-config.md,
04-operations.md, modules/{{MODULE_ID}}.md, and the other module specs). Read the module spec fully,
then interfaces, config, and data, then the specs of modules it depends on as far as needed.

Module: {{MODULE_ID}}. Code to recreate (same paths; for line ranges, replace the marker line with
the implementation at the same indentation, so the surrounding file and the tests link):
{{FILES}}
Tests that exercise it: {{TEST_FILES}}
Test command (run it from {{SCRATCH}}; {junit} is any scratch path): {{TEST_CMD}}

Honor the public surface exactly as 01-interfaces.md and the module's Public surface table name it.
Where the spec gives an exact literal, use it exactly. Where it says "not validated", do not add
validation. Where it is silent, choose the simplest behavior and log the choice. You may run the tests
as often as you like, but do not edit tests, and do not read test source to reverse-engineer expected
values: the measurement is whether the SPEC suffices. A test failure message you see while running is
fair game; record what it taught you as a spec gap.

When done, write {{SPECS}}/_meta/rebuild/{{MODULE_ID}}.json:
{"module": "{{MODULE_ID}}", "compiled": true,
 "guesses": [{"where": "...", "chose": "...", "spec_should_say": "..."}],
 "spec_bugs": ["claim id: what was wrong"], "learned_from_test_failures": ["..."], "notes": "..."}
The orchestrator runs the tests itself and scores the result; do not report pass counts.

Write {{SPECS}}/_meta/worker-reports/rebuilder-{{MODULE_ID}}.json (format: templates.md section 7)
listing every file you read. Reply with compiled yes/no and the five most important guesses.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
```
