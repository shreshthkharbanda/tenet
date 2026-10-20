# Chapter stories: the readable layer over the claims

A module spec is a ledger: hundreds of atomic claims, each true and citable, in the order of the
module's structure. Readers learn from explanation, not from ledgers. A **story** is a short chapter
written over the ledger that explains the module the way a senior engineer would on a whiteboard:
the answer first, a table of what happens when, the mechanism in a few illustrated sections, and the
traps. The reader site shows the story at the top of the chapter and the ledger below it; every
sentence of the story carries claim chips that open the claim and its code in place.

A story states nothing the ledger does not. It selects, orders, connects and illustrates. Gate G8
(`check_story.py`) enforces that mechanically; a story judge samples sentences against the claims
they cite (audit.md).

Why this shape (research summary, sources in learnings L72):
- Separate explanation from reference (Diátaxis); never mix the two in one block.
- Lead with the conclusion; headings are assertions, because readers scan headings first.
- Decision tables beat prose and trees for conditional logic on accuracy and speed; diagrams help
  where position carries meaning (sequence, topology, states); keep notation flat and label marks.
- Evidence sits beside the text (chips, popovers), never on another page.
- One concrete example with real values per rule (ladder of abstraction).
- Short sentences, one claim each; high cohesion (repeat the noun, name the actor).

## File

`_meta/story/<module>.md`, one per module. Plain Markdown with three directives. Claim chips are
claim IDs in square brackets, exactly as in the spec: `[FAILURE-006]`, ranges `[FAILURE-022]-[FAILURE-030]`.

```md
---
module: failure-handling
---
# A failing deployment sits out a cooldown that every replica can see

@minute
When a call to one deployment fails, the router decides whether to bench that deployment and for
how long [FAILURE-021]. ... (at most 120 words, at least 3 chips)

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| A call fails with status `429` and the deployment has no policy of its own | it cools down for the router's `cooldown_time` | FAILURE-031, FAILURE-042 |

## Every replica sees the same cooldown within about a second
Paragraph prose. Each sentence ends with the chips it rests on [FAILURE-006].

@figure states id=cooldown-cycle title="A deployment's cooldown cycle"
| state serving | Serving | FAILURE-011 |
| state cooling | Cooling down | FAILURE-001 |
| serving > cooling | call fails, gates pass | FAILURE-022, FAILURE-052 |
| cooling > serving | cooldown time elapsed | FAILURE-012 |

@steps cooldown-cycle
| serving | Serving | Selection keeps every deployment with no active cooldown entry [FAILURE-011]. |
| serving>cooling | A failure benches it | ... [FAILURE-052]. |

## Watch out
- A cooldown shorter than one second never reaches Redis, so sibling replicas keep sending traffic [FAILURE-006].
```

### Sections, in order
1. `# <headline>`: the chapter's thesis as one assertion (a sentence with a verb), at most 14 words.
2. `@minute`: the chapter in one minute. 60 to 120 words, at least 3 chips. Plain paragraph(s).
3. `## At a glance` (required when the module has 5 or more conditional claims, the ones that start
   with When, If, Unless, Where, While or Once): a 3-column table `When | Then | Claims`, 4 to 14
   rows, one condition per row, most common case first. The Claims cell lists IDs, comma-separated.
4. Three to six `## <assertion>` sections, each answering one question a newcomer asks about this
   module, in the order the mechanism runs. Each has 1 to 4 paragraphs and at most one figure.
5. `## Watch out`: 2 to 8 bullets, the behaviors most likely to surprise a caller, including the
   module's most consequential suspected defects (cite the defect claim).

Total length: 700 to 1,800 words. A reader finishes a story in under eight minutes.

### Writing rules (G8 checks the ones marked *)
- *Every paragraph, bullet and table row cites at least one claim; every sentence that contains a
  code literal, a number or a quoted message cites the claim it comes from, in that sentence.
- *Every backticked literal and every number in a sentence, row or figure label appears in the text
  of a claim cited there or in the code that claim cites. Never invent a value, a name or an example
  the claims do not contain; pick the example a claim gives.
- *Sentences at most 32 words (code spans excluded), paragraphs at most 120 words.
- *Every cited ID exists. Prefer this module's claims; cite another module's claim only where the
  story crosses into it.
- Headings are assertions ("Every replica sees the same cooldown within about a second"), not labels
  ("Cooldown storage").
- One term per thing, the glossary's term, used the same way in prose, tables and figure labels.
- Name the actor: "the router writes", "selection skips", never "it is written".
- Say what a value is for the first time it appears ("`cooldown_time`, the router-wide default of
  `5` seconds").
- Never restate a claim word for word: the story connects claims; the ledger holds their wording.

## Figures

`@figure <kind> id=<id> title="<what it shows, as a sentence>"` followed by pipe rows, then an
optional `@steps <id>` block. A blank line ends the rows. Figures are drawn by the reader site
(laid out by ELK, themed for light and dark, animated when the reader steps through them), so the
story gives structure only: no coordinates, no colors.

| Kind | Rows | Use for |
| --- | --- | --- |
| `flow` | `\| node <id> \| <label> \| <claims> \|`, `\| <a> > <b> \| <label> \| <claims> \|` | a decision or processing path with branches; a label ending in `?` draws a decision |
| `states` | `\| state <id> \| <label> \| <claims> \|`, `\| <a> > <b> \| <trigger> \| <claims> \|` | the lifecycle of one thing: a deployment, a pin, a reservation, a stream |
| `sequence` | `\| actor <id> \| <label> \|`, `\| <a> > <b> \| <message> \| <claims> \|` (in order) | messages between parties over time: caller, router, cache, provider |

Rules (G8 checks *):
- *Every node, state and edge cites at least one claim; message rows too. Actor rows need none.
- *At most 12 nodes or states per figure (a larger mechanism gets two figures: an overview and a
  detail). Labels at most 5 words; edge labels at most 5 words.
- *Literals and numbers in labels follow the literal rule above.
- `@steps <figure-id>` rows: `| <target> | <title> | <text with chips> |`; the target is a node id or
  an edge written `a>b`. Title each step with the label of the thing it lights. 2 to 8 steps.
- Draw the mechanism a sentence cannot carry: the order of gates, the states a thing moves through,
  the hops between parties. If the figure only names boxes the prose already lists, cut it.

## Gate G8: `check_story.py <specs> [--module ID]`

Errors: unknown claim ID; a paragraph, bullet, row or figure element with no chip; a literal or number
not found in the cited claims or their code; a sentence over 32 words or a paragraph over 120; a
missing headline or `@minute`; a minute over 120 words or under 3 chips; a missing at-a-glance table
where one is required; a figure with more than 12 nodes, a malformed row, or a step targeting nothing.

Warnings: headings that read as labels (under 4 words, no verb), a story citing none of the module's
suspected defects, story length outside 700 to 1,800 words, chips concentrated in under half of the
module's subsections (reported as coverage).

`site_data.py` compiles a story that passes into the chapter's data; one that fails is left out with
the gate's errors in `_meta/story/<module>.check.json`, so the site never shows an unchecked story.
