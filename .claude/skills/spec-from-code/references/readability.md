# Readability standard

The specs decompile code into exact claims. That is the first bridge, and the ledger is its output:
precise, citable, dense with names from the code. The second bridge runs from the ledger to a
person's understanding, and it is built for readers who will never open the code: a student, an
intern, a new graduate, a senior or staff engineer joining the team, a principal reviewing a design,
a CTO deciding what to fund, a sales engineer explaining the product. This file is the standard
that bridge is held to. Every rule below is checked by `check_story.py` (G8) unless marked
*(judged)*, in which case a story judge or a persona reader checks it (audit.md).

## How people read, and what follows from it

1. **Readers scan first and commit later.** They read headings, the first sentence of a paragraph and
   anything set apart, then decide whether to read the rest (NN/g eye tracking: the layer-cake scan
   is the most effective pattern). *So:* headings are full assertions; the first sentence of every
   paragraph states its point; nothing important hides at the end of a paragraph.
2. **Working memory holds about four new things at once** (Cowan 2001). A sentence that introduces
   three new terms and a condition overflows it. *So:* one new idea per sentence; at most one new
   term per sentence; a list or table once there are more than three parallel items.
3. **Readers link each sentence to the one before** (the given-new contract, Clark and Haviland
   1977; Gopen and Swan 1990). Old information comes first, new information last, where the stress
   falls. *So:* start a sentence with what the reader already has; end it with what is new; repeat
   the noun rather than switching synonyms (high cohesion helps novices most, McNamara 2001).
4. **Unfamiliar words cost more than long sentences.** Comprehension drops with every undefined term
   and with jargon a reader must hold unexplained. *So:* teach the key terms before the mechanism
   (Mayer's pre-training principle): a chapter opens with "Words you'll see", plain meaning first,
   code name second. A term is defined before it is used, and once defined it never changes.
5. **People understand a rule through an example** (worked-example effect, Sweller; the ladder of
   abstraction, Victor). *So:* every rule a reader must apply comes with one concrete case with real
   values, and the central mechanism gets an example timeline that plays out over time.
6. **Words and pictures together beat either alone, when they sit together** (Mayer's multimedia,
   spatial and temporal contiguity, and signalling principles). *So:* figures sit beside the text that
   explains them; steps light the part of the figure they describe; the same term labels the figure
   and the prose.
7. **Extra material hurts** (coherence and redundancy principles). *So:* no decoration, no repeated
   claims, no restating in prose what a table already shows.
8. **Experts are slowed by explanation that novices need** (the expertise-reversal effect, Kalyuga).
   One text cannot serve a student and a principal. *So:* the same chapter is written in layers, and
   the reader picks a depth: Everyone, Engineer, Expert. Each layer is complete for its reader; none
   repeats the one above.
9. **Plain language is a standard, not a style** (ISO 24495-1:2023: relevant, findable,
   understandable, usable; US Federal Plain Language Guidelines; GOV.UK content design). *So:* the
   numbers below are limits, not targets, and they are enforced.
10. **Readability formulas measure surface, not understanding** (Redish 2000). *So:* the formulas
    below are tripwires; the real test is a reader who answers questions and explains the system
    back correctly (audit.md, persona readers).

## Layers

| Layer | Reader | Contains | Code allowed |
| --- | --- | --- | --- |
| **Everyone** | anyone, including a CTO or a sales engineer | the headline, "In plain words", figures, the example timeline, the plain half of Watch out | none: no identifiers, no code formatting, no claim jargon |
| **Engineer** | someone who will work near this code | adds "In one minute", "Words you'll see", "At a glance", the mechanism sections | a few exact names, each defined in "Words you'll see" |
| **Expert** | someone who will change this code or review it | adds the ledger: every claim, its conditions and its source lines | as the claims need |

The reader site shows the layer the reader picks (the switch remembers the choice) and never hides
the evidence: every sentence keeps its claim chips, quiet in the text, opening the claim and its code.

## Limits (G8 errors unless marked)

Counting excludes claim chips. A "code span" is any backticked text; an "identifier" is a word
with an underscore, a dot or an inner capital (`retry_policy`, `litellm.Router`, `CooldownCache`) or
a call (`get()`), backticked or not.

| Where | Sentence length | Code spans | Other |
| --- | --- | --- | --- |
| Headline | at most 14 words | none | an assertion with a verb |
| In plain words | average at most 18 words, none over 26 | none, and no identifiers | 50 to 130 words; grade level at most 10 (Flesch-Kincaid, tripwire); no undefined acronym |
| Section headings | at most 14 words | none | assertions *(warning when no verb)* |
| Figure labels | at most 5 words | none, and no identifiers | the plain term from "Words you'll see" |
| In one minute | none over 32 | at most 3 | 60 to 120 words |
| Mechanism prose, steps, Watch out | average at most 22 words, none over 32 | at most 4 per 100 words *(error above 6)* | every code span is defined in "Words you'll see" or is a value (number, string, status) |
| Whole story | | | passive sentences at most 15% *(warning)*; every acronym defined at first use or in "Words you'll see" |

"Words you'll see" has one row per term: the plain term, what it means in one plain sentence, the
names it goes by in the code, and the claims that define it. Every code name used anywhere in the
story's engineer layer appears in one of its rows, so the reader always has a bridge from the word
they see to the plain idea behind it.

## Writing rules *(judged unless the table above checks them)*

- Write about what happens to a request, a deployment or a caller, in the order it happens.
- Characters as subjects, actions as verbs (Williams): "The router benches the deployment", not
  "Benching of the deployment is performed".
- Say what a value means before or instead of the value: "a five-second cooldown", then the setting
  name in "Words you'll see" if an engineer needs it.
- Numbers as numerals with units ("5 seconds", "429 Too Many Requests" the first time a status
  appears, then "429").
- No hedges the claims do not carry ("may", "typically") and no certainty they do not carry
  ("always", "never") (the story judge labels this overstated).
- No stock phrases: "it is important to note", "in order to", "leverage", "utilize", "robust",
  "seamless", "under the hood".
- Explain why when the claims say why; never invent a reason.
- For the Everyone layer, say what a business or a customer would notice: an outage, a slow reply, a
  bill, a security exposure. For the Expert layer, say exactly what the code does.

## Tests of understanding (audit.md)

- **Persona readers.** A reader agent takes a persona (student, new graduate, senior engineer,
  executive or sales engineer), reads only the layer that persona would read, then (a) explains the
  module back in its own words, (b) answers the held-out probes it can, and (c) lists every place it
  got lost. The explanation is checked against the claims; the answers against the references.
- **Pass:** no explanation states something the claims contradict; the Everyone-layer reader can say
  what the module is for, what can go wrong and who notices; the Engineer-layer reader answers at
  least half the held-out probes a story is meant to cover with no contradiction; every "got lost"
  item is fixed or answered in the story.
