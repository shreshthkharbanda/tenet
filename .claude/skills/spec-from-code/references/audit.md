# Adversarial audit briefs

Phase 7 of the skill. The pipeline's own gates measure agreement between workers who share a method;
these briefs attack the result from outside it. Each is rendered by `render_briefs.py --role <role>`
like any other brief, with extra values passed as `--set KEY=VALUE`. Outputs go to
`{{SPECS}}/_meta/audit/round-<N>/`, and `scripts/score_audit.py` turns them into `_meta/audit-report.md`.

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

Write {{SPECS}}/_meta/audit/round-{{ROUND}}/falsify-{{MODULE_ID}}.jsonl, one row per claim, appended as you go:
{"id": "...", "verdict": "holds|false|imprecise|ref_wrong", "severity": "high|medium|low",
 "evidence": "path:Lx-Ly and what the code actually does", "counterexample": "input or state, if any",
 "executed": true|false}
If you find a wrong claim outside your sample while working, append it as a row too, with
"out_of_sample": true: it is fixed like the others but not counted in the error rate. Never put it
only in your notes; notes are not read by the revision step.
Do not edit the spec or the code. Reply with verdict counts and the worst three findings.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role falsifier --module {{MODULE_ID}} --round {{ROUND}} \
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
where they exist. How to run this project's code to settle what reading cannot: {{RUN_ENV}}

Step 1, before opening any spec file: read the code in scope and write the 15 behaviors a caller or
an operator most needs to know, ranked by consequence: failure modes and what the caller sees,
retries and fallbacks, defaults that change outcomes, side effects on shared state, ordering and
concurrency hazards, limits, silent swallowing. Write them to
{{SPECS}}/_meta/audit/round-{{ROUND}}/omission-{{MODULE_ID}}.jsonl immediately, one per line:
{"rank": 1, "behavior": "precise statement with literals", "refs": ["path:Lx-Ly"], "why": "..."}
Writing the list before reading the spec is the point: it keeps the spec from shaping what you look for.

Step 2: read the spec and, for each behavior, add fields to its row (rewrite the file):
"spec_status": "stated" (a reader would get it exactly right) | "vague" (mentioned, but a reader
could not act on it: missing literal, condition, or order) | "missing" | "contradicted",
"spec_claims": ["IDs that cover it"], "note": "what the spec would need to say".

Do not edit the spec or the code. Reply with counts by spec_status and the three most consequential
omissions.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role omission --module {{MODULE_ID}} --round {{ROUND}} \
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

For each questions file, write {{EVAL}}/answers/round-0/<module>.jsonl with one row per
question, same order, appended as you go:
{"id": "...", "answer": "...", "unanswerable": false, "basis": "prior knowledge of what, in a phrase"}
For unanswerable: "unanswerable": true, "answer": "".

In your worker report (command below), list every file you read. Reply with answered vs unanswerable counts per module.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role control --module all --snapshot {{CONTROL_DIR}} \
    --output <each file you wrote>[:<claim count>] --read-from {{CONTROL_DIR}}/_work/reads-all.txt \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
Keep every scratch file (the read list included) under {{CONTROL_DIR}}/_work/: anything you create
elsewhere counts as a file you touched outside your snapshot.
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

Write {{EVAL}}/audit/round-{{ROUND}}/judge-audit.jsonl: {"id": "...", "verdict": "...", "note": "..."},
appended as you go. Do not read {{EVAL}}/judgments/ or any spec file. Reply with verdict counts.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role judge-auditor --module all --round {{ROUND}} \
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
check_coverage.py, and would score well in score_probes.py. Examples of the kind of thing to try (do not
stop at these): refs that resolve but point at irrelevant lines; symbol dumps that satisfy symbol
coverage without saying anything; bare-path refs that satisfy file coverage; claims that are
unfalsifiable ("handles errors appropriately"); copying the same claim under many IDs; hedged
claims that a lenient judge would accept; anything in the probe flow that lets the spec writer
learn held-out answers; ways a worker could falsify its own report and pass verify_reports.py.
If an earlier round's red-team report exists ({{SPECS}}/_meta/audit/round-*/redteam.md), first re-run
each of its exploits against the current scripts and say which are closed and which still pass. Then
attack the newer defenses: the eval dir (_meta/run.json names it), G5 with --transcripts (accesses a
transcript cannot show: imports, scripts that open files they do not name, paths built at runtime),
G7 evidence checks that pass without testing their claim (assert True, a bare try/except, assertions
about something other than what the `# text:` line says, a check that never reaches the entry point),
the verdict checks in score_probes.py, waivers, and the decision ledger in apply_claim_edits.py.

For each exploit: demonstrate it on the copy (run the gate and show it passes), rate severity
(how likely an honest-but-rushed worker produces this by accident, and how much it would mislead a
reader), and propose the smallest mechanical check that closes it. Write
{{SPECS}}/_meta/audit/round-{{ROUND}}/redteam.md. Do not edit the skill or the real specs. Reply with the exploits
ranked by severity.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role redteam --module all --round {{ROUND}} \
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

Then, from the spec alone, write {{SPECS}}/_meta/audit/round-{{ROUND}}/reader.md:
1. The lifecycle of this request, end to end, as numbered steps, each naming the spec claim IDs it
   relies on: {{READER_SCENARIO}}
2. Three things you would get wrong if you changed this code tomorrow, based on what you read.
3. Every place the spec confused you, contradicted itself, or used a term it did not define, with
   the file and claim ID.
Keep it under 1200 words. Your lifecycle will be checked against the code by someone else.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role reader --module all --round {{ROUND}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## Lifecycle checker

<!-- brief:lifecycle-checker -->
```
You are checking a newcomer's explanation of a code path against the code. Repo: {{REPO}} (commit
{{COMMIT}}). Explanation: {{SPECS}}/_meta/audit/round-{{ROUND}}/reader.md (section 1 is the lifecycle; the steps cite
spec claim IDs, which you may ignore). Scenario: {{READER_SCENARIO}}

Trace the scenario in the code yourself, executing it where reading is not decisive: {{RUN_ENV}} For each numbered step write a row to
{{SPECS}}/_meta/audit/round-{{ROUND}}/lifecycle-check.jsonl:
{"step": 1, "verdict": "correct|incorrect|vague|missing_step_before", "evidence": "path:Lx-Ly", "note": "..."}
Then add rows with "verdict": "missing" for important steps the explanation skipped entirely. A wrong
explanation means the spec taught it wrong, so be exact. Reply with verdict counts.
Report: write your worker report with the CLI, not by hand (the gate verifies its schema):
  python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role lifecycle-checker --module all --round {{ROUND}} \
    --output <each file you wrote>[:<claim count>] --read-from <a file listing every path you read> \
    [--note "..."] [--bug "path:START-END|what looks unintended|how you know"]
This replaces any other instruction above about the report's file name or format.
```

## Story audit (Phase 9, before anyone reviews from the site)

A story is written over the claims; G8 proves its literals and citations mechanically. Two things G8
cannot see: a sentence whose words match its claims but whose meaning does not ("always" where the
claim says "when Redis is attached"), and a story that, read alone, leads a reader to a wrong answer.
Per module: one story judge (sentences against claims), one story-only reader (answers the probes
from the story alone, in a snapshot), one scorer (answers against reference answers). Then
`story_probe.py score --specs $SPECS`; it fails on any distorted or unsupported sentence, more than
3% overstated sentences, or any contradicted answer, and the narrator revises with every row that is
not supported (an overstated sentence is the usual cause of a contradicted answer: L79).
```
python3 $SKILL_DIR/scripts/story_probe.py snapshot --specs $SPECS --module <m> --out $SCRATCH/story-snap-<m>
python3 $SKILL_DIR/scripts/render_briefs.py --role story-reader --module <m> --snapshot $SCRATCH/story-snap-<m> ...
python3 $SKILL_DIR/scripts/render_briefs.py --role story-judge --module <m> ...   # and --role story-scorer
```

<!-- brief:story-judge -->
```
You are checking a chapter story against the specification claims it cites. The story is the part
of the spec people will actually read, so a sentence that says more, less or other than its claims
misleads every reader. Repo: {{REPO}} (commit {{COMMIT}}). Story: {{SPECS}}/_meta/story/{{MODULE_ID}}.md.
Claims: {{CLAIMS_HOME}} and, for IDs of other prefixes, the spec file that holds
them under {{SPECS}}. You may read the code a claim cites. Never read anything under the eval dir.

Judge exactly these units, one row each, so every module is judged on the same ground (L78): every
sentence of In plain words, In one minute and every paragraph; every row of Words you'll see (term and
meaning read as one sentence); every At-a-glance row read as one sentence; every figure step, every
timeline row and every path step; every Watch-out bullet. For each, find the claims it cites (a range
[X-010]-[X-014] cites all of them) and label it:
- supported: the cited claims say this, with the same conditions and scope;
- overstated: the claims say less (a condition dropped, "always" or "every" where they say "when",
  a default stated as the only behavior);
- distorted: the claims say something different (wrong order, wrong actor, wrong value, wrong cause);
- unsupported: no cited claim says it (it may be true; the story still may not say it uncited).
Write one row per sentence to {{SPECS}}/_meta/audit/story/{{MODULE_ID}}.jsonl:
{"sentence": "<the sentence>", "ids": ["..."], "verdict": "supported|overstated|distorted|unsupported",
 "note": "for anything but supported: what the claims actually say, quoting them"}
Do not edit the story or the spec. Reply with the counts per verdict and the three worst rows.
Report: python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role story-judge --module {{MODULE_ID}} --round {{ROUND}} \
  --output {{SPECS}}/_meta/audit/story/{{MODULE_ID}}.jsonl --read-from <a file listing every path you read>
This replaces any other instruction above about the report's file name or format.
```

<!-- brief:story-reader -->
```
You are an engineer who has just read one chapter of a system's specification: the chapter story in
{{SPEC_SNAPSHOT}}/story.md. Read it once, fully. Then answer every question in
{{SPEC_SNAPSHOT}}/questions.jsonl using only what the story says. Read nothing else: no other file,
no code, no web; the story is all you have, and the point is to measure what it teaches.
For each question write one row to {{EVAL}}/answers/story/{{MODULE_ID}}.jsonl:
{"id": "<question id>", "answer": "<your answer, specific: values, names, order>",
 "basis": "story" | "not_in_story", "cites": ["<claim IDs from the story sentences you used>"]}
Use "not_in_story" when the story does not say enough to answer; then give your best guess in
"answer" anyway and say it is a guess. Do not guess silently: a confident wrong answer is the worst
outcome. Keep scratch notes, if any, under {{SPEC_SNAPSHOT}}/_work/.
Report: python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role story-reader --module {{MODULE_ID}} --round {{ROUND}} \
  --snapshot {{SPEC_SNAPSHOT}} --output {{EVAL}}/answers/story/{{MODULE_ID}}.jsonl --read-from <a file listing every path you read>
This replaces any other instruction above about the report's file name or format.
```

<!-- brief:story-scorer -->
```
You are scoring answers that a reader gave from a short chapter story, against reference answers
established from the code. Questions and reference answers: {{EVAL}}/probes/{{MODULE_ID}}.jsonl.
Answers: {{EVAL}}/answers/story/{{MODULE_ID}}.jsonl. Do not read the story or any spec file: you
judge the answers, not the text behind them. For every question write one row to
{{EVAL}}/judgments/story/{{MODULE_ID}}.jsonl:
{"id": "...", "verdict": "agree|partial|contradict|not_in_story", "note": "..."}
- agree: the answer matches the reference on every point the question asks.
- partial: correct as far as it goes, but missing part of what the reference states.
- contradict: the answer states something the reference contradicts, whatever its "basis" says.
- not_in_story: the reader said the story does not cover it and did not commit to a wrong answer
  (a guess labelled as a guess that happens to be wrong is not_in_story, not contradict).
In "note", for contradict, quote the conflicting part of the answer and of the reference.
Report: python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role story-scorer --module {{MODULE_ID}} --round {{ROUND}} \
  --output {{EVAL}}/judgments/story/{{MODULE_ID}}.jsonl --read-from <a file listing every path you read>
This replaces any other instruction above about the report's file name or format.
```

### Persona readers (the readability test; readability.md, "Tests of understanding")

A persona reader reads only the layer its persona would read, then explains the module back. The
explanation is the test: a reader who understood can say what the part is for, how it works and
what can go wrong, in their own words, without contradicting the claims. Run one per module with the
Everyone layer (a sales engineer, or a CTO for the system story); the story-only reader above is the
Engineer-layer test.
```
python3 $SKILL_DIR/scripts/story_probe.py snapshot --specs $SPECS --module <m> --lens everyone --no-questions --out $SCRATCH/persona-<m>
python3 $SKILL_DIR/scripts/render_briefs.py --role persona-reader --module <m> --snapshot $SCRATCH/persona-<m> \
  --set "PERSONA=a sales engineer who explains the product to customers and does not read code" ...
python3 $SKILL_DIR/scripts/render_briefs.py --role teachback-judge --module <m> ...   # after the reader
```

<!-- brief:persona-reader -->
```
You are {{PERSONA}}. A colleague handed you one chapter of a system's documentation:
{{SPEC_SNAPSHOT}}/story.md. Read it once, fully, the way you would before a meeting. Read nothing
else: no other file, no code, no web.
Then write {{SPECS}}/_meta/audit/story/{{MODULE_ID}}.persona.md with three parts:
1. "In my words": explain this part of the system to someone like you, in at most 300 words: what
   it is for, how it works, and what can go wrong and who would notice. Write it from memory of the
   chapter, in your own words, and number each statement (1., 2., ...). Each statement makes one
   point. Where you rely on a chapter sentence, add the claim IDs that sentence carried.
2. "Where I got lost": every term you did not understand, every sentence you had to read twice,
   every place you would have asked a question, quoting the words. Write "nothing" only if true.
3. "What I would tell a customer": two or three sentences you would actually say.
Do not try to sound expert: a misunderstanding written down is exactly what this test is for.
Report: python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role persona-reader --module {{MODULE_ID}} --round {{ROUND}} \
  --snapshot {{SPEC_SNAPSHOT}} --output {{SPECS}}/_meta/audit/story/{{MODULE_ID}}.persona.md --read-from <a file listing every path you read>
This replaces any other instruction above about the report's file name or format.
```

<!-- brief:teachback-judge -->
```
You are checking what a reader understood from a chapter, against the specification. A persona
reader read only the plain layer of {{SPECS}}/_meta/story/{{MODULE_ID}}.md and wrote
{{SPECS}}/_meta/audit/story/{{MODULE_ID}}.persona.md. Claims: {{CLAIMS_HOME}} and,
for other prefixes, the spec file that holds them under {{SPECS}}; you may read the code a claim
cites. Never read the eval directory.
For each numbered statement in "In my words" and each sentence of "What I would tell a customer",
write a row to {{SPECS}}/_meta/audit/story/{{MODULE_ID}}.teachback.jsonl:
{"statement": "<the statement>", "verdict": "correct|vague|wrong|unsupported",
 "story_cause": "<the story sentence that led the reader there, quoted, or empty>", "note": "..."}
- correct: the claims say this (plain wording is fine; precision is not required, truth is);
- vague: not false, but too unspecific to act on;
- wrong: the claims contradict it (a reader who believed it would make a wrong decision);
- unsupported: the claims do not say it either way.
Then, for every item under "Where I got lost", add a row {"lost": "<quoted words>", "fix": "<the
plain-words change to the story that would have prevented it>"}.
Reply with counts per verdict and every wrong row with its story_cause.
Report: python3 {{SKILL_DIR}}/scripts/write_report.py --specs {{SPECS}} --role teachback-judge --module {{MODULE_ID}} --round {{ROUND}} \
  --output {{SPECS}}/_meta/audit/story/{{MODULE_ID}}.teachback.jsonl --read-from <a file listing every path you read>
This replaces any other instruction above about the report's file name or format.
```
