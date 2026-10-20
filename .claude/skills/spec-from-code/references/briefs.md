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
How to run this project's code here (to confirm an entry point or a test command): {{RUN_ENV}}

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
Get proposed cut points from `python3 {{SKILL_DIR}}/scripts/split_file.py {{REPO}} <path> --max-loc 3500`
(or use those the Scope lists). They are cut at definition boundaries and chosen to keep calling
neighbors together, but size drives them, not meaning. Read the method names around each cut: if a
cut separates definitions that form one responsibility (a shared name prefix, a helper and its only
caller), move it to another boundary from the `boundaries` list in `split_file.py --json`. The gate
rejects a range that starts anywhere else. You may also merge adjacent ranges. A module may
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
{{REFS}}/templates.md section 7, then reply with: module count, total in-scope LOC,
modules over 6000 LOC (if any), and the three biggest risks.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role surveyor --module all \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
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
- {{REFS}}/templates.md (claim grammar, confidence rules, precision ladder, writing
  rules, and the modules/<id>.md template; copy the template's frontmatter and section headings exactly)
- {{REFS}}/implicit-decisions.md (walk every item for this module)

Method:
1. Read the tests first; they pin behavior. A test file over ~2000 lines is not read whole: grep it for
   your public symbols and read the matching tests. Then read every in-scope file (or range)
   completely, in chunks if needed, and say in your report notes which parts you read in chunks.
   Public surface created at runtime counts: names bound by assignment from a factory, setattr loops,
   registration tables, decorators that wrap or rename, and attributes generated from data files. List
   every resulting public name in the Public surface table with a ref to where it is bound, because
   these names never appear as definitions and a reader cannot find them otherwise.
2. Grep for callers of each public symbol outside the module (what callers rely on is contract). A
   claim about who calls what ("the Router calls X", "only tests use Y") must cite the call sites
   themselves as refs, found by search, not inferred from names; "no production caller" claims are
   universal claims (see templates.md) and need the search scope stated.
3. Open dependencies only as far as needed to state this module's behavior; what you did not trace is
   {inferred} or {gap}, never {confirmed}. Where reading leaves you unsure, execute: copy what you need
   to {{SCRATCH}}/extract-{{MODULE_ID}}/ and run a throwaway harness there (never in the repo). How to
   run this project's code here: {{RUN_ENV}}
   If behavior looks unintended, state what the code does in the normative sections anyway, and add it
   under "## Suspected defects" with the evidence (see templates.md).
4. Write {{SPECS}}/modules/{{MODULE_ID}}.md. Every fact is a claim with an ID {{PREFIX}}-001, -002, ...
   and a verified ref (path:START-END relative to the repo root, or path::Symbol). Aim for one claim per
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
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role extractor --module {{MODULE_ID}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## 3. Cross-cutting extractors (four, parallel with module extractors)

One template, four focus blocks. `render_briefs.py --role crosscut --kind <interfaces|data|config|operations>`
fills `{{XC_*}}` from the focus block below.

<!-- brief:crosscut -->
```
You are writing one cross-cutting file of a behavioral specification of a codebase: the {{XC_KIND}}
file. The module specs are finished and have passed lint and coverage. Your file is the system-wide
INDEX of one concern across them, plus the facts that no module owns. Every fact lives in exactly one
place: the module that owns the code. Restating module facts here makes two copies that drift apart.

Repo: {{REPO}} (commit {{COMMIT}}). Output: {{SPECS}}/{{XC_FILE}} (frontmatter kind: {{XC_KIND}},
prefix: {{XC_PREFIX}}). Scope: {{SCOPE_NOTE}}
Module map: {{SPECS}}/_meta/modules.json. System survey: {{SPECS}}/_meta/survey.md (read first).
How to run this project's code here (execute rather than infer when a fact is cheap to check): {{RUN_ENV}}

Focus:
{{XC_FOCUS}}

Before writing, read {{REFS}}/templates.md (grammar, confidence, precision ladder,
writing rules, and the template for {{XC_FILE}}; copy its frontmatter and headings exactly) and
{{REFS}}/implicit-decisions.md.

How to write it:
0. If {{SPECS}}/{{XC_FILE}} already exists, it is an earlier version: convert it rather than starting
   over. Never delete or renumber a claim ID: other files and answers point to them, and the full lint
   fails on a dangling pointer. A claim whose fact a module claim owns becomes a pointer that keeps its
   ID and refs, e.g. "- [CFG-123] {confirmed} `path:10-20` Fallback depth is specified in [FAIL-045]."
   Keep a claim as it is only when no module claim states its fact.
1. Read the module specs under {{SPECS}}/modules/ (their Public surface, Configuration, State and data,
   and Error handling sections first). Build the index the template asks for (entry points, error
   catalog, settings, stores...), with one row per item and, in each row, the module claim IDs that
   specify it ([MOD-NNN]).
2. Write a claim of your own ({{XC_PREFIX}}-001, -002, ...) only for a fact no module claim states:
   precedence across modules, values read in code outside the specified scope (constants, globals,
   environment read at import), system-wide invariants, and gaps between modules. Read the source to
   verify each one; refs are path:START-END or path::Symbol, relative to the repo root.
3. If a module claim is wrong or missing something you need, do not restate it correctly here: list
   it in your worker report notes as "module claim X-NNN: <problem>" so it is fixed at its owner, and
   point to it anyway.
A claim of yours that cites lines a module owns must carry that module's claim ID, or the ownership
gate (check_ownership.py) counts it as a restatement and fails the file above 20%. Do not modify source
or module specs. No tool or model mentions. Redact secrets as [REDACTED] plus a gap.

Finish by running:
  python3 {{SKILL_DIR}}/scripts/lint_specs.py {{SPECS}} --repo {{REPO}} --only {{XC_FILE}}
and fixing every error. Write {{SPECS}}/_meta/worker-reports/{{XC_KIND}}-all.json (format:
templates.md section 7) with an accurate claim count and every file you read. Reply with claim counts
by confidence and the three facts you are least sure about.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role {{XC_KIND}} --module all \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
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

## 2c. Verifier (executable evidence for confirmed claims; G7)

<!-- brief:verifier -->
```
You are backing claims of a behavioral specification with executed evidence. A claim marked
{confirmed} was written by someone who read the code; about one in three such claims turned out wrong
or incomplete when someone ran it (most often where it states what code outside the cited lines does:
what the provider call receives, how a dependency logs, what a sibling sync/async path does, whether a
value is copied or shared). Your job is to run each claim, and either back it with a check script or
correct it.

Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}} ("{{MODULE_NAME}}"), spec
{{SPECS}}/modules/{{MODULE_ID}}.md. Your claims (only these): {{CLAIM_LIST}}
How to run this project's code here: {{RUN_ENV}}

For each claim:
1. Read the claim, its refs, and the code around them. Find the PUBLIC entry point a caller would use
   to observe the behavior (a Router method, a CLI command, an HTTP route), not the helper.
2. Write {{SPECS}}/_meta/evidence/{{MODULE_ID}}/check_<CLAIM-ID>.py. First lines, exactly:
     # claim: <CLAIM-ID>
     # text: <the claim's text as it will stand in the spec, on one line, refs omitted>
   The script drives the entry point with fakes only at the outer boundary (provider HTTP, Redis,
   clock), so it runs code the claim's refs cite (the gate fails a check that executes none of those
   lines, or whose body names nothing the claim states), asserts every observable the claim states (values, exact messages, exception types, order,
   what is NOT done), covers the boundary its words imply ("only", "unless", "never", "always": test
   the case on each side), prints what it observed, and exits 0 only if the claim holds. Then attack
   what the claim leaves unsaid, because that is where verified claims still fail: the dependency
   failing (store or provider raising, timing out, circuit open), input of the wrong type or shape
   (None, string for number, unparseable), early cancellation or close (a stream dropped before its
   first read), the sync/async and sibling entry points, and a second instance in the same process.
   If one of these changes the outcome a caller sees, the claim is incomplete: correct it. It must run
   with `python -P` the way the run environment above says (interpreter, working directory,
   environment variables), in under 60 seconds, and never write into the repo.
3. Run it. Then exactly one of:
   - It passes: done.
   - It fails because the claim is wrong or incomplete: write the corrected claim text (same ID, same
     refs unless they were wrong) as a row of
     {{SPECS}}/_meta/reconcile/decisions-verify-{{MODULE_ID}}-{{CHUNK}}.jsonl:
     {"row": -1, "verdict": "contradiction", "edits": [{"file": "modules/{{MODULE_ID}}.md", "id": "<CLAIM-ID>",
      "text": "<corrected text>"}], "evidence": "check_<CLAIM-ID>.py: what it observed"}
     then make the script's `# text:` line and assertions match the corrected text, and run it again.
   - An existing test already pins exactly this behavior through the entry point: append
     {"id": "<CLAIM-ID>", "test": "<path>::<test name>", "text": "<claim text>"} to
     {{SPECS}}/_meta/evidence/{{MODULE_ID}}/tests.jsonl after running that test.
   - It cannot be checked by execution here (needs real network, real time, true concurrency):
     append {"id": "<CLAIM-ID>", "reason": "..."} to {{SPECS}}/_meta/evidence/{{MODULE_ID}}/unverifiable.jsonl
     and, if it is {confirmed} only because it was read, say so in the reason.
Never edit spec files directly (other verifiers work on this module too); decision rows are applied
by a script. Do not modify the repo. If a check reveals behavior that looks unintended, keep the claim
describing what the code does and report the bug.

Finish by running
  python3 {{SKILL_DIR}}/scripts/check_evidence.py {{SPECS}} --module {{MODULE_ID}} --python <interpreter> \
    --cwd <working dir> --env NAME=VALUE ...   (all three as the run environment above gives them)
and make every check you wrote pass (stale-text errors for claims you corrected clear once the rows
are applied; list those IDs in your report notes). Reply with counts: passed, corrected, test-pinned,
unverifiable, and the three corrections that matter most.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
each check script and each decision row as soon as it is final. If you are told you were resumed,
list what exists under {{SPECS}}/_meta/evidence/{{MODULE_ID}}/ and continue from there.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role verifier --module {{MODULE_ID}}-{{CHUNK}} \
    --output <each file you wrote> --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## 2d. Narrator (a module's story, in reading layers; G8)

<!-- brief:narrator -->
```
You are writing the readable chapter for one module of a behavioral specification, for people who
will never open the code: a student, an intern, a new graduate, a senior or staff engineer joining
the team, a principal reviewing a design, a CTO deciding what to fund, a sales engineer explaining
the product. The module spec is a ledger of exact claims, each citing code. You write the story over
it, in layers the reader chooses between: Everyone (plain words and pictures, no code at all),
Engineer (the mechanism, with a few exact names, each bridged to a plain term), Expert (the ledger,
which already exists). You select, order, connect and illustrate claims; you never add a fact.

Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}} ("{{MODULE_NAME}}").
Read first, fully: {{SKILL_DIR}}/references/readability.md (the standard, and why each rule exists)
and {{SKILL_DIR}}/references/story.md (the format, the layers, the figure syntax). Then read
{{SPECS}}/modules/{{MODULE_ID}}.md (the ledger you explain) and {{SPECS}}/00-overview.md (the system,
its main paths and the glossary, whose terms you use). You may open the source lines a claim cites to
understand it. Never read the eval directory or any answer or story snapshot.
{{SCOPE_NOTE}}

Write {{SPECS}}/_meta/story/{{MODULE_ID}}.md in the format of story.md. Work in this order:
1. Find the one idea a newcomer must leave with, and write it as the headline.
2. Write "In plain words" for someone who knows what an AI provider and a web request are and nothing
   else: what this part is for, how it works as one picture in words, and what a customer or the
   business would notice when it goes wrong. No code names at all; spell out every acronym.
3. List the terms the chapter needs in "Words you'll see", plain meaning first, code names second.
4. Write the mechanism sections in the order it runs, each heading an assertion, each paragraph
   leading with its point. Prefer the plain term; use a code name only where an engineer needs the
   exact name, and only once it is in Words you'll see.
5. Draw the central mechanism (states, flow or sequence, plain labels, with steps), and give it one
   example timeline: concrete deployments and real values from the claims, played out over time. When
   a rule turns on one input with many values (which status codes do what, what each setting value
   does), give it a table figure, one row per value, so a reader scans for their case.
6. Write At a glance (When/Then, most common case first) and Watch out (plain words, what surprises
   a caller, including the most consequential suspected defects).
Keep every condition a claim states. A story audit judged earlier stories sentence by sentence: the
most common fault was a dropped condition ("the check applies" where the claim says "when the router
was built with it"), and readers then generalized the rule to cases it does not cover and answered
wrongly. When you shorten a rule, keep its condition or say "in the usual case" and put the
exception in At a glance or Watch out. Name the edge cases a reader would otherwise guess wrong.
Persona readers (a sales engineer reading only the Everyone layer) got lost in earlier stories in the
same few ways; write against each:
- a count you do not list ("nine checks", then five named): list them all, or drop the number;
- two polarities for one decision ("passes the gate" in one place, "the gate refuses" in another):
  say what happens to the thing ("benches the deployment", "does not bench it");
- a status whose usual meaning differs from this one (a 429 that means "no deployment is free",
  not "you hit your rate limit"): say what it means here, in plain words;
- nobody said to notice: say who sees a failure (the caller's error, a header, a log line, an alert)
  as the claims say, or that the claims name no alert;
- a term the Everyone layer leans on with no row in Words you'll see (a routing group, a tier, a
  hook); and rows the story never uses, which the gate rejects.
A row of Words you'll see is a definition: say what the thing is, cite the claim that defines it,
and leave what it does under conditions to the sections. Definitions were the most overstated rows
in round 3 ("the filters run on this path" for a path where they sometimes do not). A number a claim
gives as a default is "5 seconds by default", never "5 seconds" (the gate warns).
{{AUDIT_NOTES}}

Run the gate and fix every error and every warning you can, until it passes:
  python3 {{SKILL_DIR}}/scripts/check_story.py {{SPECS}} --module {{MODULE_ID}}
Its rules are strict on purpose: a value not in the claims you cite is an error; code in the Everyone
layer is an error; a code name not bridged in Words you'll see is an error. Fix the text, never the
meaning. Never edit spec files. If explaining the module exposes a claim that is unclear, contradicts
another or misses a case, report it as a note "module claim {{PREFIX}}-NNN: <the problem>".
Durability: write the story file early and rewrite it as you go; if you are told you were resumed,
read the file and the gate's output and continue.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role narrator --module {{MODULE_ID}} \
    --output {{SPECS}}/_meta/story/{{MODULE_ID}}.md --read-from <a file listing every path you read> \
    [--note "..."]
This replaces any other instruction above about the report's file name or format.
```

## 2f. Story fixer (targeted repair after a story judge; G8)

After a story judge's round, the rows not marked "supported" name exactly what to repair. A fresh
fixer reads the story, those rows and the claims they name, and changes only those sentences: far
cheaper than a narrator rewrite, and it cannot introduce new material for the next judge to find
(L84). Use a narrator rewrite instead when a persona reader got lost or explained something wrongly.

<!-- brief:story-fixer -->
```
You are repairing named sentences in one readable story of a behavioral specification. A story judge
labelled every sentence of the story against the claims it cites; each row not marked "supported"
is a mistake. Fix those, and nothing else.

Story: {{SPECS}}/_meta/story/{{MODULE_ID}}.md. Judge rows: {{SPECS}}/_meta/audit/story/{{MODULE_ID}}.jsonl.
Claims: {{CLAIMS_HOME}} and, for other prefixes, the spec file that holds them under {{SPECS}}. You may
read the code a claim cites. Never read anything under the eval dir, or earlier audit rounds.
Read first: {{SKILL_DIR}}/references/story.md (format and layers) and the writing rules in
{{SKILL_DIR}}/references/readability.md.

For each row whose verdict is not "supported", read its note and the claims it names, then:
- overstated: put back the condition the claim states, or say "by default" or "in the usual case"
  and move the exception to At a glance or Watch out;
- distorted: rewrite the sentence to say what the claims say;
- unsupported: cite the claim that says it (search the spec for it), or cut the clause no claim
  supports.
A row of Words you'll see is a definition: say what the thing is and cite the claim that defines it;
leave behavior that holds only under conditions to the sections.
Change only what a row needs, plus anything the change makes inconsistent elsewhere in the story
(the same fact in a figure step, At a glance or Watch out). Do not restructure, add sections or add
facts. Keep the story's terms: one term per thing.

Run the gate until it reports 0 errors, and fix its warnings where you can:
  python3 {{SKILL_DIR}}/scripts/check_story.py {{SPECS}} --module {{MODULE_ID}} --repo {{REPO}}
Edit only the story file. If a row's note shows the claim itself is wrong or looser than its code,
keep the story faithful to the claim and report "module claim <ID>: <the problem>".
Reply with the gate's summary line, one line per row (fixed, or kept and why), and any module claim
notes.
Report: python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role story-fixer --module {{MODULE_ID}} \
  --round {{ROUND}} --output {{SPECS}}/_meta/story/{{MODULE_ID}}.md --read-from <a file listing every path you read> \
  [--note "..."]
```

## 2e. System narrator (the book's opening and the plain walkthroughs; G8)

<!-- brief:system-narrator -->
```
You are writing the opening of a book about one system, for every reader from a student to a CTO or
a sales engineer: what the system is for, how a request moves through it in plain words, and what
can go wrong for the business. You select, order, connect and illustrate claims; you never add a fact.

Repo: {{REPO}} (commit {{COMMIT}}).
Read first, fully: {{SKILL_DIR}}/references/readability.md and {{SKILL_DIR}}/references/story.md
(the section "System story" is your format). Then read {{SPECS}}/00-overview.md (the system, the
main paths you will retell, the glossary), every module story under {{SPECS}}/_meta/story/ (written
by the module narrators; reuse their plain terms so the book speaks one language), and the module
specs under {{SPECS}}/modules/ where you need a claim. Never read the eval directory or any snapshot.

Write {{SPECS}}/_meta/story/_system.md:
- a headline: the system's purpose as one assertion;
- "In plain words": the whole system for anyone, 50 to 130 words, no code names, every acronym
  spelled out;
- "Words you'll see": the terms every chapter relies on (model group, deployment, and so on);
- one section per main path of the overview, in the overview's order: a heading that says what
  happens, one or two plain paragraphs, and an @path block retelling every step of that path in plain
  words, numbered exactly as the overview numbers it, each step citing the claims the overview step
  cites (or narrower ones);
- a section on what can go wrong for the business (outages, slow replies, cost, security exposure),
  citing the suspected defects that matter most, with one figure that shows the request lifecycle or
  the failure path in plain labels;
- Watch out: the top risks, in plain words.
Run the gate until it passes:
  python3 {{SKILL_DIR}}/scripts/check_story.py {{SPECS}} --module _system
Never edit spec files or module stories. Report unclear or conflicting claims as notes
"module claim <ID>: <the problem>".
Report: python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role system-narrator --module all \
  --output {{SPECS}}/_meta/story/_system.md --read-from <a file listing every path you read> [--note "..."]
This replaces any other instruction above about the report's file name or format.
```

## 3b. Pair judge (parallel, before the Reconciler)

<!-- brief:pairjudge -->
```
You are judging pairs of claims, written independently by different spec writers, that describe the
same lines of code. Your decisions are applied to the specs by a script, so be exact.

Repo: {{REPO}} (commit {{COMMIT}}). Pairs: rows {{SLICE}} (0-based, end exclusive) of
{{SPECS}}/_meta/overlaps.jsonl. Each row has "a" and "b" with file, id, refs, text, plus "kind"
(duplicate or same-code). How to run this project's code if reading is not enough: {{RUN_ENV}}

For each row, open the code at both refs and decide:
- distinct: the claims describe different behaviors of the same code, and both are right. No edit.
- contradiction: they disagree on something a caller could observe. Fix the wrong one (or both).
- duplicate: they state the same fact. Keep the full statement in the claim whose file owns the code
  (the module spec over 01-04 cross-cutting files; for two modules, the one whose scope holds the
  lines) and rewrite the other as a pointer that keeps its ID and confidence, e.g.
  "`update_settings` applies only the runtime-updatable keys; the exact list is in [RSELECT-152]."
  If the two differ in a detail, make the kept one correct first.
- unresolvable: the code itself is inconsistent or ambiguous; describe it for the human.

Write {{SPECS}}/_meta/reconcile/decisions-{{SLICE_NAME}}.jsonl, one row per pair, appended as you go:
{"row": N, "verdict": "distinct|contradiction|duplicate|unresolvable",
 "edits": [{"file": "modules/x.md", "id": "RSELECT-152", "text": "full new claim text, without the id,
           confidence, or refs", "confidence": "confirmed|inferred|gap (optional, to change it)",
           "refs": ["optional replacement refs"]}],
 "evidence": "path:START-END and what the code does", "question": "only for unresolvable"}
An edit replaces the claim's text (and confidence or refs if given); the ID never changes. Do not edit
spec files yourself. Write {{SPECS}}/_meta/worker-reports/pairjudge-{{SLICE_NAME}}.json (format:
{{REFS}}/templates.md section 7, with every file you read and any suspected_bugs you noticed). Reply
with counts by verdict.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role pairjudge --module {{SLICE_NAME}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## 4. Reconciler (one, after all extractors pass lint and coverage)

<!-- brief:reconciler -->
```
You are reconciling independently written module specifications into one coherent specification set
and writing its top layer. Read everything under {{SPECS}} (probes, answers and judgments live
elsewhere and are not yours to read). Repo: {{REPO}} (commit {{COMMIT}}). Survey: {{SPECS}}/_meta/survey.md.
Scope of the specification: {{SCOPE_NOTE}}
To settle a contradiction by running the code: {{RUN_ENV}}

Tasks, in order:
1. Contradictions and duplicates were decided by pair judges and applied by script. Finish what the
   script could not, from {{SPECS}}/_meta/reconcile/:
   - conflicts.json: claims that two judges edited differently. Open the code, choose (or merge into)
     the correct text, preferring the variant that points straight at the owning module claim, and
     edit the claim line in place (keep its ID).
   - applied.json "pointer_chains": repoint each pointer at the final owning claim.
   - applied.json "tables_to_review": table rows that mention an edited claim; make each row's values
     agree with the claim it cites, or replace the value with the claim ID.
   - {{SPECS}}/_meta/questions.md: for each question, add a {gap} claim to the owning module if none
     covers it.
2. Cross-links. Where a module spec says "see module X" or describes a dependency's behavior, add the
   concrete claim ID cross-reference `[X-NNN]` so a reader can jump. Do not duplicate claims across
   modules; one fact lives in the module that decides it, and other modules point at it.
3. Write {{SPECS}}/00-overview.md per the template in {{REFS}}/templates.md: purpose,
   system map table, 3-7 main paths as ordered steps citing claim IDs end to end, global invariants as
   SYS claims with refs, cross-cutting concerns, glossary, reading order. Write for an engineer new to
   the codebase who has 15 minutes; this is the short book the module specs are appendices to.
4. Write {{SPECS}}/_meta/gaps.md: every {gap} claim in every spec, grouped by module, with ref and
   question, plus what would resolve it (a test to write, a person to ask, a dependency to read).
4b. Suspected defects. Read every worker report under {{SPECS}}/_meta/worker-reports/ (notes,
   suspected_bugs) and every {gap} and Implementation note. Where one describes behavior that looks
   unintended, make sure the owning module spec has it as a claim under "## Suspected defects" (add the
   section if missing; the claim states what happens, why it looks unintended, and the impact). When
   two modules flag the same code, keep one claim in the owning module and cross-reference it from the
   other. Then run `python3 {{SKILL_DIR}}/scripts/collect_defects.py {{SPECS}}`.
5. Write {{SPECS}}/INDEX.md per the template (under 100 lines). Put the status table between
   <!-- status:begin --> and <!-- status:end --> with fidelity and rebuild "pending"; apply_status.py
   fills it from measured results later.

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
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role reconciler --module all \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
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

Write {{N_PROBES}} probes to {{EVAL}}/probes/{{MODULE_ID}}.jsonl, one JSON object per line:
{"id": "{{PREFIX}}-P01", "module": "{{MODULE_ID}}", "category": "validation|error|branch|side_effect|config|interface|data|concurrency|default",
 "edge": true, "question": "...", "reference_answer": "...", "refs": ["path:START-END"],
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
How to run this project's code here: {{RUN_ENV}} An executed reference answer beats a read one; mark it verified_by: execution. Execute through the
public entry point the question names (e.g. `Router.acompletion`), not the helper that implements one
step: ordering bugs live between steps. A test counts as verification only if it drives that same entry
point; a unit test of a helper does not (LiteLLM: a test of the key-stripping helper "verified" that
forged reservations cannot be refunded, while the real call path refunds before stripping).

Do not read other modules' probes or anything under {{SPECS}}. Do not modify any file except your
probe file. Write your worker report (command below) listing every file you read. Reply with the
probe count by category and difficulty.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role prober --module {{MODULE_ID}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
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

Write {{EVAL}}/answers/round-{{ROUND}}/{{MODULE_ID}}.jsonl, one object per question, same
order:
{"id": "...", "answer": "exact answer, quoting literals from the spec", "unanswerable": false,
 "claims_used": ["{{PREFIX}}-012", "CFG-004"], "note": "optional: where the spec was ambiguous"}

For an unanswerable probe set "unanswerable": true, answer "", and say in note what the spec would
need to say. For a partially answerable probe, answer what the spec supports and say what is missing.

In your worker report (command below), list every file you read (all must be under {{SPEC_SNAPSHOT}};
this brief itself is there too). The gate checks your session's actual file accesses, not only the list. Reply with: answered, partial, unanswerable counts.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role answerer --module {{MODULE_ID}} --round {{ROUND}} --snapshot {{SPEC_SNAPSHOT}} \
    --output <each file you wrote>[:<claim count>] --read-from {{SPEC_SNAPSHOT}}/_work/reads-{{MODULE_ID}}.txt \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
Keep every scratch file (the read list included) under {{SPEC_SNAPSHOT}}/_work/: anything you create
elsewhere counts as a file you touched outside your snapshot.
This replaces any other instruction above about the report's file name or format.
```

## 7. Judge (one per module per round)

<!-- brief:judge -->
```
You are judging whether answers derived from a specification agree with reference answers derived
from the code. Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}}.

Inputs:
- probes with reference answers and refs: {{EVAL}}/probes/{{MODULE_ID}}.jsonl
- spec-only answers: {{EVAL}}/answers/round-{{ROUND}}/{{MODULE_ID}}.jsonl

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

Write {{EVAL}}/judgments/round-{{ROUND}}/{{MODULE_ID}}.jsonl:
{"id": "...", "verdict": "agree|contradict|gap|probe_invalid", "note": "one line: the distinguishing fact",
 "spec_defect": "optional: a spec inaccuracy you noticed that did not change the verdict"}
Record spec_defect whenever the spec states something the code contradicts or leaves out, even when
the answer still agrees (e.g. the right outcome attributed to the wrong cause). These are routed to
revisers mechanically; do not bury them in the note.

Do not read or edit any spec file; your job is comparison, not repair. Do not read earlier rounds'
judgments or answers: each round is measured fresh, and a verdict copied for consistency carries the
earlier judge's mistakes forward (the gate checks). Write your worker report (command below) listing
every file you read. Reply with the verdict counts.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role judge --module {{MODULE_ID}} --round {{ROUND}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## 8. Reviser (Extractor in revise mode; one per failing module per round)

<!-- brief:reviser -->
```
You are revising the specification of one module after fidelity probing found contradictions and
gaps. Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}}, prefix {{PREFIX}}.
Spec to revise: {{SPECS}}/modules/{{MODULE_ID}}.md, which you own and edit directly. Other revisers run
in parallel, so NEVER edit the shared files (00-overview.md, 01-interfaces.md, 02-data.md,
03-config.md) or another module's spec: when a failure's root cause is a claim there, write the fix as
a row of {{SPECS}}/_meta/reconcile/decisions-revise-{{MODULE_ID}}-round-{{ROUND}}.jsonl, in the format
{"row": -1, "verdict": "contradiction", "edits": [{"file": "03-config.md", "id": "CFG-123", "text":
"<full new claim text>"}], "evidence": "path:START-END ..."}; the orchestrator applies all such rows
with the single-writer script after every reviser finishes. The text replaces the whole claim block,
sub-bullets included: to keep sub-bullets, put them in the text as further lines ("...\n  - item"),
indented deeper than the claim's own bullet. Prefer turning a wrong shared claim into a pointer to
your module's correct claim.
Failures: {{SPECS}}/_meta/revise/round-{{ROUND}}/{{MODULE_ID}}.jsonl. Each row has a "source":
- probe: a revision-split probe the spec answered wrongly (contradict) or not at all (gap), with the
  question, reference answer, refs, the spec-only answer, and the judge's note;
- answer_note / defect_note: the answer agreed, but the answerer or judge saw the spec was silent,
  ambiguous, or self-contradictory there;
- falsifier: a sampled claim shown false or imprecise, with the evidence and counterexample;
- omission: a high-consequence behavior the spec states vaguely, omits, or contradicts;
- lint: a placeholder template without rendering, a table row carrying untracked values or a value
  found in neither the claims it cites nor their code, or a claim dense with code names: rewrite it
  words first (what happens, in plain words, then the exact names an engineer needs, at most 4), with
  the same meaning, ID and refs; if it states two things, keep one under the ID and add the other as
  a new claim (templates.md, "Natural language first");
- rebuild: a guess an implementer had to make from this spec, or a spec bug found while rebuilding;
- note: another worker (a cross-cutting writer, a falsifier, the reconciler) reported this claim as
  wrong or incomplete while working on its own file; verify it in the code before acting on it.
- evidence: the claim's check script (_meta/evidence/<module>/check_<ID>.py) fails, is stale, passes
  only on a re-run (flaky: harden it), or is hollow (it runs none of the code the claim cites, or names
  nothing the claim states: make it drive that code, or correct the claim's refs).
  Whenever you change a claim that has a check script, update the script's `# text:` line and
  assertions to the new text and run it; a changed claim with an unchanged check fails the gate.
When you confirm a behavior by running it, keep the script as that claim's evidence instead of
throwing it away: save it as {{SPECS}}/_meta/evidence/{{MODULE_ID}}/check_<ID>.py with the two header
lines (`# claim: <ID>` and `# text: <the claim's final text, one line, refs omitted>`), make it exit 0
only when the claim holds, and run it the way the run environment says. Evidence accumulates this way
at no extra cost (L67). Run
  it; correct the claim if the code disagrees, or fix the check if it tests the wrong thing, and keep
  its `# text:` line equal to the claim's final text.
The probe rows are revision-split only; a separate held-out set you will never see is scored
afterwards, so fixing exactly these questions is not the goal. Fixing what they reveal is.

Read {{REFS}}/templates.md (grammar, rules) and
{{REFS}}/implicit-decisions.md first.

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

Never renumber, reuse or delete a claim ID (answers, pointers and evidence checks cite them; lint
fails on an ID that existed at the last round's backup and is gone). Rewrite in place instead: a gap
you resolved from code becomes {confirmed} with the answer; a suspected defect that proves false
becomes a claim stating what the code actually does. Run
`python3 {{SKILL_DIR}}/scripts/lint_specs.py {{SPECS}} --repo {{REPO}} --only modules/{{MODULE_ID}}.md`
(add `--only 01-interfaces.md` etc. for any other file you edited) until clean. Write
{{SPECS}}/_meta/worker-reports/reviser-{{MODULE_ID}}-round-{{ROUND}}.json. Reply with: failures by
root-cause class, claims rewritten, claims added, references you judged wrong.
Durability: the container running you can restart mid-task, and anything not on disk is lost. Write
your output file early and save it after each section (append each probe, answer, or verdict as soon
as it is final). If you are told you were resumed, check your output file first and continue from it.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role reviser --module {{MODULE_ID}} --round {{ROUND}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
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
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role rebuilder --module {{MODULE_ID}} --snapshot {{SCRATCH}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```
