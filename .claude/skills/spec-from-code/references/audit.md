# Adversarial audit briefs

Phase 7 of the skill. The pipeline's own gates measure agreement between workers who share a method;
these briefs attack the result from outside it. Each is rendered by `render_briefs.py --role <role>`
like any other brief, with extra values passed as `--set KEY=VALUE`. Outputs go to
`{{SPECS}}/_meta/audit/`, and `scripts/score_audit.py` turns them into `_meta/audit-report.md`.

Roles: falsifier (per module) · omission (per module) · control (all modules, no spec, no code) ·
judge-auditor (one) · redteam (one) · reader (one) · lifecycle-checker (one).

## Falsifier

<!-- brief:falsifier -->
```
You are auditing a behavioral specification by trying to prove its claims false. You are not
checking that claims are plausible; you are hunting for the claims that are wrong. Assume the writer
was rushed and confident.

Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}} ("{{MODULE_NAME}}"). Code in scope:
{{FILES}}
Claims to attack (a fixed random sample; do not swap in others): {{SAMPLE_FILE}}, rows with
"module": "{{MODULE_ID}}". Each row has id, confidence, refs, text.

For every claim:
1. Open each ref and the code around it. Then look for what would make the claim false: another
   branch, an early return, an exception path, a config flag or default that changes it, the sync
   vs async twin of the function, a caller that passes something the claim ignores, a literal that
   differs by one character, an ordering that differs, "always"/"never" where a condition exists.
2. Where cheap, execute: copy what you need to {{SCRATCH}}/falsify-{{MODULE_ID}}/ and run a harness
   there (never in the repo). An executed counterexample is the strongest evidence. How to run this
   project's code here: {{RUN_ENV}}
3. Verdict, one of:
   - holds: you tried and could not break it.
   - false: the code does something else in a case a caller can reach. Give the case.
   - imprecise: true as far as it goes, but omits a condition or literal that changes behavior for a
     reachable input (a reader would act wrongly on it).
   - ref_wrong: the behavior may be real, but the cited lines do not show it.
   Severity: high (a caller relying on it would get wrong results or miss a failure), medium, low.

Write {{SPECS}}/_meta/audit/falsify-{{MODULE_ID}}.jsonl, one row per claim, appended as you go:
{"id": "...", "verdict": "holds|false|imprecise|ref_wrong", "severity": "high|medium|low",
 "evidence": "path:Lx-Ly and what the code actually does", "counterexample": "input or state, if any",
 "executed": true|false}
Do not edit the spec or the code. Reply with verdict counts and the worst three findings.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role falsifier --module {{MODULE_ID}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## Omission hunter

<!-- brief:omission -->
```
You are auditing a behavioral specification for what it leaves out. Probes sample behavior at random;
you look for the behaviors that matter most and check whether the spec states them precisely.

Repo: {{REPO}} (commit {{COMMIT}}). Module: {{MODULE_ID}} ("{{MODULE_NAME}}"). Code in scope:
{{FILES}}
Spec: {{SPECS}}/modules/{{MODULE_ID}}.md plus {{SPECS}}/01-interfaces.md, 02-data.md, 03-config.md
where they exist.

Step 1, before opening any spec file: read the code in scope and write the 15 behaviors a caller or
an operator most needs to know, ranked by consequence: failure modes and what the caller sees,
retries and fallbacks, defaults that change outcomes, side effects on shared state, ordering and
concurrency hazards, limits, silent swallowing. Write them to
{{SPECS}}/_meta/audit/omission-{{MODULE_ID}}.jsonl immediately, one per line:
{"rank": 1, "behavior": "precise statement with literals", "refs": ["path:Lx-Ly"], "why": "..."}
Writing the list before reading the spec is the point: it keeps the spec from shaping what you look for.

Step 2: read the spec and, for each behavior, add fields to its row (rewrite the file):
"spec_status": "stated" (a reader would get it exactly right) | "vague" (mentioned, but a reader
could not act on it: missing literal, condition, or order) | "missing" | "contradicted",
"spec_claims": ["IDs that cover it"], "note": "what the spec would need to say".

Do not edit the spec or the code. Reply with counts by spec_status and the three most consequential
omissions.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role omission --module {{MODULE_ID}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## No-spec control answerer

<!-- brief:control -->
```
You are a control in an experiment. You will answer questions about a software project WITHOUT any
specification and WITHOUT the source code, using only what you already know about the project in
general. The experiment measures how many questions can be answered from prior knowledge; a high
score here means the questions do not test the specification. Answer honestly: guess where you have
a real basis, and mark the rest unanswerable.

You may read only the files in {{CONTROL_DIR}} (question files named <module>.questions.jsonl and
this brief). Do not read any other file. Do not search the web. Do not run code.

For each questions file, write {{SPECS}}/_meta/answers/round-0/<module>.jsonl with one row per
question, same order, appended as you go:
{"id": "...", "answer": "...", "unanswerable": false, "basis": "prior knowledge of what, in a phrase"}
For unanswerable: "unanswerable": true, "answer": "".

Write {{SPECS}}/_meta/worker-reports/control-all.json with role "answerer", "snapshot":
"{{CONTROL_DIR}}", and every file you read. Reply with answered vs unanswerable counts per module.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role control --module all --snapshot {{CONTROL_DIR}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## Judge auditor

<!-- brief:judge-auditor -->
```
You are re-judging a sample of fidelity verdicts to measure how reliable the original judges were.
You do not see their verdicts. Be strict: the point is to find leniency.

Repo: {{REPO}} (commit {{COMMIT}}). Sample: {{SAMPLE_FILE}} (rows with id, module, question,
reference_answer, refs, answer). For each row, decide:
- agree: the answer states the same observable behavior; literals, codes, orderings, and conditions
  match. Different wording is fine. Hedging ("may", "usually", "depending on") where the code is
  deterministic is not agreement.
- contradict: the answer asserts a different behavior.
- gap: the answer is unanswerable or missing the distinguishing fact.
- probe_invalid: the reference answer is wrong or the question is not answerable from observable
  behavior. Open the refs to check before using this.

Write {{SPECS}}/_meta/audit/judge-audit.jsonl: {"id": "...", "verdict": "...", "note": "..."},
appended as you go. Do not read {{SPECS}}/_meta/judgments/. Reply with verdict counts.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role judge-auditor --module all \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## Red team

<!-- brief:redteam -->
```
You are red-teaming a specification pipeline's quality gates. The pipeline claims its gates make a
bad spec fail. Your job is to show where a bad spec passes.

Skill: {{SKILL_DIR}} (read SKILL.md, references/validation.md, references/templates.md, and every
script in scripts/). Real specs to experiment on: copy {{SPECS}} to {{SCRATCH}}/redteam-specs/ and
work only on the copy. Repo: {{REPO}} (read-only).

Find exploits: edits to a spec that are wrong, empty, or misleading, yet pass lint_specs.py,
coverage.py, and would score well in score_probes.py. Examples of the kind of thing to try (do not
stop at these): refs that resolve but point at irrelevant lines; symbol dumps that satisfy symbol
coverage without saying anything; bare-path refs that satisfy file coverage; claims that are
unfalsifiable ("handles errors appropriately"); copying the same claim under many IDs; hedged
claims that a lenient judge would accept; anything in the probe flow that lets the spec writer
learn held-out answers; ways a worker could falsify its own report and pass verify_reports.py.

For each exploit: demonstrate it on the copy (run the gate and show it passes), rate severity
(how likely an honest-but-rushed worker produces this by accident, and how much it would mislead a
reader), and propose the smallest mechanical check that closes it. Write
{{SPECS}}/_meta/audit/redteam.md. Do not edit the skill or the real specs. Reply with the exploits
ranked by severity.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role redteam --module all \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## Reader

<!-- brief:reader -->
```
You are an engineer new to this codebase, reading its specification to understand it. You have the
specification only: do not open source code. Read {{SPECS}}/INDEX.md and {{SPECS}}/00-overview.md
first, then at most four module specs of your choice, following the reading order.

Then, from the spec alone, write {{SPECS}}/_meta/audit/reader.md:
1. The lifecycle of this request, end to end, as numbered steps, each naming the spec claim IDs it
   relies on: {{READER_SCENARIO}}
2. Three things you would get wrong if you changed this code tomorrow, based on what you read.
3. Every place the spec confused you, contradicted itself, or used a term it did not define, with
   the file and claim ID.
Keep it under 1200 words. Your lifecycle will be checked against the code by someone else.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role reader --module all \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## Lifecycle checker

<!-- brief:lifecycle-checker -->
```
You are checking a newcomer's explanation of a code path against the code. Repo: {{REPO}} (commit
{{COMMIT}}). Explanation: {{SPECS}}/_meta/audit/reader.md (section 1 is the lifecycle; the steps cite
spec claim IDs, which you may ignore). Scenario: {{READER_SCENARIO}}

Trace the scenario in the code yourself. For each numbered step write a row to
{{SPECS}}/_meta/audit/lifecycle-check.jsonl:
{"step": 1, "verdict": "correct|incorrect|vague|missing_step_before", "evidence": "path:Lx-Ly", "note": "..."}
Then add rows with "verdict": "missing" for important steps the explanation skipped entirely. A wrong
explanation means the spec taught it wrong, so be exact. Reply with verdict counts.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role lifecycle-checker --module all \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```
