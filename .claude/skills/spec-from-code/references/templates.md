# Spec templates, claim grammar, and writing rules

Every file in this document is what a worker writes. The orchestrator never hand-writes specs; it
runs scripts and dispatches workers. Workers copy these templates exactly, because `lint_specs.py`
checks frontmatter keys, section headings, and claim grammar mechanically.

Contents
1. Claim grammar
2. Confidence rules
3. Precision ladder
4. Writing rules (language-neutral, agent-neutral, observable)
5. Layout of the specs directory
6. Templates: INDEX.md, 00-overview.md, 01-interfaces.md, 02-data.md, 03-config.md,
   04-operations.md, modules/<id>.md, _meta/gaps.md, _meta/questions.md, _meta/confidence-report.md
7. Worker report format

---

## 1. Claim grammar

A claim is one bullet, one sentence, one trigger, one observable outcome:

```
- [PREFIX-NNN] {confidence} `path:START-END`, `path::Symbol` Text.
```

- `PREFIX` is the module's prefix from `_meta/modules.json` (or `SYS`, `IF`, `DATA`, `CFG`, `OPS` for the
  cross-cutting files). `NNN` is three or four digits, unique within the prefix, never reused and never
  renumbered. When a claim is wrong, rewrite its text; when it is obsolete, delete it. A new fact gets the
  next unused number.
- `{confidence}` is exactly one of `{confirmed}`, `{inferred}`, `{gap}` (section 2).
- Refs are backticked, comma separated, relative to the repo root. Forms: `path:START-END` (line numbers, e.g. `src/a.py:88-104`; an `L` prefix is accepted), `path:LINE`,
  `path::Symbol` (the symbol name must occur in that file), or a bare `path`. Prefer line ranges for
  behavior and symbol refs for interface facts; both are verified by the linter. Every confirmed or
  inferred claim needs at least one ref. A gap may have none.
- Text starts after the refs. Cross-reference other claims inline as `[AUTH-012]`; the linter checks
  that they resolve.

Why this shape: atomic claims make every later step mechanical. Coverage maps files to claims, probes
target single claims, judges compare one fact at a time, and a human reviewing the spec can accept or
reject one line.

Good:
```
- [AUTH-014] {confirmed} `src/auth/session.py:88-104` When a session token is older than
  `SESSION_TTL_SECONDS` (default `3600`), validation raises `SessionExpired` before any database read.
```
Bad (two facts, no trigger, no literal):
```
- [AUTH-014] {confirmed} `src/auth/session.py` Sessions expire after a while and are cleaned up.
```

Tables are allowed and encouraged for decision logic and state machines, but every row that states a
fact must also appear as, or point to, a claim ID so it is traceable. The convention: put the claim ID in
the first column.

## 2. Confidence rules

- `{confirmed}`: you read the code path and the text follows from it with no interpretation beyond
  reading. A test that pins the behavior also counts as confirmation; cite it in Test evidence.
- `{inferred}`: the behavior is strongly suggested (naming, a comment, a doc, a partial read, a call into
  a dependency you did not open) but you did not trace the whole path. Say in the text what the inference
  rests on: "…(inferred from the docstring; the retry loop itself lives in a third-party client)".
- `{gap}`: you could not determine the behavior and a human or a deeper pass needs to. Write it as the
  open question it leaves, with the ref to where the uncertainty arises. Gaps are not failures. They are
  the most valuable lines in the spec for a reviewer, because they are where the code's behavior is
  invisible from the code.

Existing documentation (README, docstrings, wiki) is evidence for `{inferred}`, never for `{confirmed}`.
Docs drift; code does not.

## 3. Precision ladder

Natural language is ambiguous (Dijkstra, EWD667). Specs stay in prose because prose is what humans
review, but every claim should sit as high on this ladder as the fact allows:

1. Exact literal in backticks: error strings, status codes, header names, regexes, defaults, units,
   env var names, file paths, enum values, exit codes, version pins that affect behavior.
2. Ordered check lists: "Checks run in this order; the first failing check wins: (1) …, (2) …".
3. Tables for decision logic and state machines: inputs as columns, outcome as the last column, one
   claim ID per row.
4. Given / When / Then for behaviors with setup, trigger, and observable result.
5. Pseudo-predicates for conditions: "when `retries_remaining == 0 and status in {502, 503, 504}`".
6. Plain prose, only for purpose, rationale, and context.

Numbers get units. Time gets a timezone or "monotonic". Sizes say bytes or characters. Ranges say
inclusive or exclusive. Ordering says stable or unstable. Defaults say where they are set.

## 4. Writing rules

- **Observable behavior only** (fidelity-probe observability rule). Specify inputs, outputs, return
  values, raised errors, persisted changes, emitted events and logs that carry data, calls to other
  systems, and config-dependent branching. Do not specify private helper structure, variable names, or
  which internal function calls which, except in Implementation notes.
- **Language-neutral.** Describe behavior, not syntax. Public identifiers (functions, classes, routes,
  commands, flags, env vars, table names) are part of the interface and are named exactly. Private
  identifiers appear only inside refs. No code transcription; code fences longer than 20 lines are
  flagged by the linter. Short literals in backticks are good.
- **Agent-neutral and self-contained.** Never mention a model, a tool, or this process in the spec. Each
  module spec must make sense to a reader who opens only it plus `INDEX.md`. Define terms where used or
  in the glossary. Specs are consumed by retrieval as well as by people, so a chunk pulled out of the
  middle of a file should still be interpretable.
- **Normative vs informative.** Behaviors, Validation rules, Error handling, State and data, External
  interactions, Configuration, Concurrency and ordering are normative. Implementation notes are
  informative unless an implementation choice is observable (wire format, hash algorithm, persistence
  format, sort stability, library whose behavior leaks through, timeout values): then it becomes a
  normative claim in the relevant section, and the note says why it is load-bearing.
- **Capture implicit decisions.** Read `implicit-decisions.md` before writing and again before
  finishing. Anything on that list that the module decides must be stated, even when the decision is "no
  retry", "no timeout", "no validation". Absence of a safeguard is a behavior.
- **Redact.** Never copy credentials, keys, tokens, personal data, or internal hostnames that look like
  secrets. Write `[REDACTED]` and add a gap. The linter scans for common secret shapes and fails the file.
- **Tests are evidence.** Read the module's tests first. A test pins behavior better than a comment.
  Cite tests in Test evidence as `claim id -> test ref`.
- **Callers tell you the contract.** Grep for callers of the public surface. What callers rely on is
  behavior even when it looks incidental.
- **Do not edit source.** Workers write only under the specs directory (and a scratch copy for rebuilds).
- **Specify bugs, then flag them.** If the code does something that looks unintended, the normative
  sections state what it does (a spec that silently "fixes" a bug misleads a reviewer and fails a
  rebuild), and the optional Suspected defects section says why it looks wrong. Suspected defects are
  collected across modules into `_meta/suspected-defects.md` for the human review.

## 5. Layout

```
specs/
  INDEX.md               under 100 lines: what this is, reading order, status table, how to re-validate
  00-overview.md         SYS: purpose, system map, main paths end to end, invariants, glossary
  01-interfaces.md       IF: every external entry point and the error catalog
  02-data.md             DATA: stores, schemas, migrations, invariants, formats
  03-config.md           CFG: every setting, default, precedence, where read
  04-operations.md       OPS: build, test, run, deploy, observability, dependencies (optional for libraries)
  modules/<id>.md        leaf behavioral specs, one per module in _meta/modules.json
  _meta/                 machine state: inventory, modules, reports, probes, answers, judgments, gaps
```

## 6. Templates

### INDEX.md (written by the Reconciler, regenerated at the end)

```markdown
# <Project> specification

Behavioral specification of <project> at commit `<sha>` (<date>). Recovered from the code and its
tests; status per module below. Code is the implementation, this is the description of what it does.

## How to read this
1. `00-overview.md` for purpose, the system map, and the main paths end to end (15 minutes).
2. `01-interfaces.md` for the exact external contract.
3. The modules on the main paths, in the order listed in the overview's Reading order.
4. `02-data.md`, `03-config.md`, `04-operations.md` as reference.
5. `_meta/gaps.md` for what the code does not reveal and someone must decide.

## Status
| Spec | Claims (confirmed / inferred / gap) | File coverage | Held-out fidelity | Rebuild | Status |
|---|---|---|---|---|---|
| modules/<id>.md | 84 / 9 / 3 | 100% | 93% | 41/41 tests | validated |

Status meanings: validated (held-out fidelity >= 90%, no held-out contradictions), provisional (>= 75%),
weak (< 75%), draft (not yet probed).

## Re-validating
Run `gate.py specs --repo . --round <n>` from the spec-from-code skill. Stale commit warnings mean the
code moved; re-run extraction with `--update`.
```

### 00-overview.md

```markdown
---
kind: overview
prefix: SYS
commit: <sha>
status: draft
---
# <Project>: overview

## Purpose
What the system is for and who calls it, in one paragraph. Then the one-sentence job of each module.

## System map
| Module | Prefix | Responsibility | Depends on | Entry points |
|---|---|---|---|---|

Then a narrative of how the modules fit, with cross-module claims:
- [SYS-001] {confirmed} `path:START-END` <system-level fact, e.g. the single process model, the request lifecycle owner>

## Main paths
For each primary use case (3 to 7), the end-to-end path as an ordered list of steps, each step naming
the module and the claims that govern it: "3. The router validates the body ([IF-004]) and hands a
Command to the engine ([ENG-012])."

## Global invariants
- [SYS-0xx] {confirmed} `...` Facts that hold across modules: idempotency guarantees, ordering,
  consistency, what is never logged, what is always authenticated.

## Cross-cutting concerns
Errors, logging, auth, retries, time, randomness, feature flags, tenancy: where each is decided and the
claim IDs that pin it.

## Glossary
Term: definition, as used in this codebase (not the textbook meaning).

## Reading order
Numbered list of module specs for a new engineer, with one line on why each comes where it does.
```

### 01-interfaces.md

```markdown
---
kind: interfaces
prefix: IF
commit: <sha>
status: draft
---
# External interfaces

## Entry points
One subsection per surface (CLI, HTTP, library API, events consumed, jobs, signals). For each entry
point: name, inputs with types and constraints, outputs, errors, side effects, idempotency, auth.
Every row is a claim:
- [IF-001] {confirmed} `src/cli.py:40-71` `tenet check <path> [--format text|json|sarif]` exits `0` when
  no finding has severity `PROVEN`, `1` otherwise, `2` on usage error.

## Error catalog
| ID | Condition | Error type / code / message (exact) | Surface | Retryable |
|---|---|---|---|---|
| [IF-0xx] | … | … | … | … |
```

### 02-data.md

```markdown
---
kind: data
prefix: DATA
commit: <sha>
status: draft
---
# Data

## Stores
Every durable store (database, files, caches, queues, object storage) and who owns writes.

## Schemas
Tables / collections / file formats with fields, types, nullability, keys, indexes that affect behavior,
and how they change (migrations, versioning, compatibility rules). Claims cite the schema or migration.

## Invariants
Facts that must hold in the data regardless of code path, with the claim that enforces each.
```

### 03-config.md

```markdown
---
kind: config
prefix: CFG
commit: <sha>
status: draft
---
# Configuration

## Settings
| ID | Setting | Source (env / flag / file key) | Type | Default | Read by | Effect |
|---|---|---|---|---|---|---|
Every setting is one claim row. Include undocumented ones found in code.

## Precedence
- [CFG-0xx] {confirmed} `...` Flag beats env beats file beats built-in default, or whatever the code does.
Also: when settings are read (startup vs per call), validation of settings, and what happens on invalid.
```

### 04-operations.md

```markdown
---
kind: operations
prefix: OPS
commit: <sha>
status: draft
---
# Operations

## Build
## Test
## Run
## Deploy (if present)
## Observability (logs, metrics, traces: what carries data, formats)
## Dependencies
Third-party libraries whose behavior is load-bearing, with version pins and why they matter.
```

### modules/<id>.md

```markdown
---
kind: module
module: <id>
prefix: <PREFIX>
commit: <sha>
status: draft
scope:
  - <glob>
---
# <Module name> (<PREFIX>)

## Purpose
Two to five sentences. What this module decides that no other module decides.

## Scope and boundaries
Files in scope (summarize by directory). What is deliberately out of scope and which module owns it.
Inbound dependencies (who calls this) and outbound (what this calls), by module id.

## Public surface
| Entry point | Kind | Inputs | Outputs | Errors | Claims |
|---|---|---|---|---|---|
One row per public function, class, command, route, handler, or event this module exposes.

## Behaviors
Grouped by entry point or feature, as claims. Given/When/Then where setup matters.

## Validation rules
Ordered. "Checks run in this order; the first failing check wins." Exact messages. What is NOT validated.

## Error handling
Table: condition -> what is raised/returned (exact type, code, message), what is logged, what is
retried (count, backoff, which errors), what is swallowed. Claims per row.

## State and data
What is read, written, cached, and when. Keys, formats, TTLs, invalidation. Invariants maintained.

## External interactions
Network, filesystem, environment, clock, randomness, subprocesses, other modules. For each: when,
with what, timeouts, failure behavior.

## Configuration
Settings this module reads (cross-ref `03-config.md` IDs) and the behavior each changes.

## Concurrency and ordering
Threads, async, locks, queues, ordering guarantees, idempotency, race windows observed in code.

## Implementation notes
Informative. Algorithms, data structures, library choices. Mark anything load-bearing as a normative
claim above and say why here.

## Open questions and gaps
List of the `{gap}` claims with one line each on what would resolve them.

## Test evidence
| Claim | Test | What it pins |
|---|---|---|

## Suspected defects
Optional. Behavior that looks unintended: it contradicts its own docstring or name, a sibling path
(sync vs async), a caller's evident expectation, or the module's purpose. The normative sections
still state what the code DOES; this section says why it looks wrong, as claims:
- [PFX-0xx] {confirmed} `path:START-END` <what happens>. Looks unintended because <evidence>. Impact: <who
  hits it and how>.
```

### _meta/gaps.md, _meta/questions.md, _meta/confidence-report.md (Reconciler, from scripts + specs)

- `gaps.md`: every `{gap}` claim across all specs, grouped by module, with its ref and the question.
- `questions.md`: contradictions between specs that the Reconciler could not resolve from code, probe
  contradictions that survived revision, and decisions the code leaves to deployment.
- `confidence-report.md`: per module: claims by confidence, file and symbol coverage, held-out fidelity,
  rebuild result, status, and the three weakest areas in one line each.

## 7. Worker report format

Every worker ends by writing `_meta/worker-reports/<role>-<module>[-round-N].json`:

```json
{
  "role": "extractor | surveyor | interfaces | data | config | operations | reconciler | prober | answerer | judge | rebuilder | reviser",
  "module": "<id or 'all'>",
  "outputs": [{"path": "specs/modules/<id>.md", "claims": 87}],
  "files_read": ["src/auth/session.py", "tests/test_session.py"],
  "notes": "anything the orchestrator should know: suspected dead code, a file too large to read fully, a dependency whose behavior could not be traced"
}
```

Use absolute paths in `outputs` and `files_read`. `verify_reports.py` checks these against the filesystem. Report what you did, not what you intended;
a report that claims 87 claims when 40 parse fails the gate and the module is re-run.
