# Stories: the readable layers over the claims

The ledger (a module spec) decompiles code into exact claims. A **story** carries those claims the
rest of the way, into a reader's understanding. It is written for a person who will never open the
code, at the depth they choose: **Everyone** (a CTO, a sales engineer, a student), **Engineer**
(someone who will work near this code), **Expert** (the ledger itself). The reader site shows the
layer the reader picks, with every sentence's claim chips opening the claim and its code in place.

A story states nothing the ledger does not. It selects, orders, connects and illustrates. Gate G8
(`check_story.py`) enforces the evidence, layer and length rules mechanically; the story audit
(audit.md) checks meaning with a story judge and comprehension with persona readers. The standard
behind every rule, and the reading research it rests on, is `readability.md`. Read it first.

There are two kinds of story:
- a **module story**, `_meta/story/<module>.md`, one per module;
- the **system story**, `_meta/story/_system.md`, the book's opening: what the system is for, its
  main paths told in plain words step by step, and what can go wrong.

## Module story

```md
---
module: failure-handling
---
# A failing deployment sits out a short cooldown that every server can see

@plain
When one of the AI providers behind the router fails, the router can stop sending it traffic for a
few seconds [FAILURE-021]. This pause is called a cooldown. ... (50 to 130 words, no code)

@minute
When a call to one deployment fails, the router decides whether to bench that deployment and for
how long [FAILURE-021]. ... (60 to 120 words, at most 3 code names, each defined below)

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| cooldown | a short pause during which the router sends a deployment no traffic | `deployment:<id>:cooldown` | FAILURE-001 |
| cooldown time | how long a cooldown lasts, 5 seconds unless set | `cooldown_time` | FAILURE-005 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| A call fails with status 429 (too many requests) and the group has other deployments | the deployment cools down | FAILURE-031, FAILURE-042 |

## Every server sees the same cooldown within about a second
Prose: what happens, in the order it happens, each sentence ending with its chips [FAILURE-006].

@figure states id=cooldown-cycle title="A deployment's cooldown, from first failure to recovery"
| state serving | Serving traffic | FAILURE-011 |
| state cooling | Cooling down | FAILURE-001 |
| serving > cooling | call fails, checks pass | FAILURE-022, FAILURE-052 |
| cooling > serving | cooldown time passes | FAILURE-012 |

@steps cooldown-cycle
| serving | Serving traffic | The router picks only deployments that are not cooling down [FAILURE-011]. |
| serving>cooling | A failure starts a cooldown | ... [FAILURE-052]. |

## A burst of errors trips the cooldown
@figure timeline id=burst title="Example: three quick failures, then recovery"
| lane a | Deployment A |
| lane b | Deployment B |
| 0s | a | call fails with 429 | cooling down | FAILURE-031 |
| 0s | b | takes A's traffic | serving | FAILURE-011 |
| 5s | a | cooldown time passes | serving | FAILURE-012 |

## Watch out
- A cooldown shorter than one second stays on one server, so the others keep sending traffic [FAILURE-006].
```

### Layers and what each part may contain

| Part | Layer | Code | Purpose |
| --- | --- | --- | --- |
| `# headline` | Everyone | none | the chapter's thesis as one assertion, at most 14 words |
| `@plain` "In plain words" | Everyone | none, no code names at all | what this part of the system is for, how it works in one picture, what a customer or the business would notice when it goes wrong; spell out every acronym |
| `@minute` "In one minute" | Engineer | at most 3 names | the mechanism in one paragraph, for an engineer who reads nothing else |
| `## Words you'll see` | term and meaning: Everyone; code names: Engineer | names in the third column only | the bridge: plain term, plain meaning, the names it goes by in the code, the claims that define it. Every code name the story uses appears here, and every term the Everyone layer leans on (a persona reader names each undefined one). Order rows by first use. |
| `## At a glance` | Engineer | values and defined names | the module's conditional behavior as When/Then rows, most common case first (required when the module has 5 or more conditional claims) |
| section lead (the first paragraph of every section) | Everyone | none | at most 60 words: the section's point in plain words, so a reader who chose Everyone sees heading, lead and figure and never a bare heading |
| `## <assertion>` sections | heading and figure: Everyone; prose after the lead: Engineer | prose: at most 4 code spans per 100 words, each a value or a defined name | 3 to 6 sections in the order the mechanism runs, each answering one question a newcomer asks |
| `@figure` | Everyone | none in titles, labels, steps | the mechanism a sentence cannot carry (see Figures) |
| `## Watch out` | Everyone | none | 2 to 8 bullets: what surprises a caller, in plain words, including the most consequential suspected defects |

### Writing rules (G8 checks the ones marked *)
- *Evidence: every paragraph, bullet, table row and figure element cites claims that exist; every
  sentence with a value cites the claim it comes from; every value and name is in a cited claim or
  the code that claim cites. Never invent a value, a name or an example; use the claims' examples.
- *Layers: the Everyone layer has no code formatting and no code names (no `snake_case`, no
  `dotted.names`, no `CamelCase`, no `calls()`), and spells out every acronym the first time.
- *Every code name in the Engineer layer is a value (a number, a quoted string, a status code) or
  appears in "Words you'll see". Prefer the plain term in prose once it is defined.
- *Length: plain words 50 to 130 words, averaging at most 18 words a sentence, none over 26; grade
  level at most 10 (Flesch-Kincaid, a tripwire); Engineer sentences average at most 22, none over 32;
  paragraphs at most 120 words.
- **Keep every condition** (the story audit's most common finding). When a claim says "when Redis is
  attached", "only for the async path", "unless the request opts out", the sentence keeps it, or says
  "in the usual case" and the exception goes to Watch out or the ledger. A reader generalizes every
  rule you state to every case you do not mention; a missing condition becomes a wrong answer.
- **Name the edge cases a reader would otherwise guess wrong**: a zero, a missing value, a
  sub-second time, a second instance, a failure of the store. Put them in At a glance or Watch out.
- One term per thing, the glossary's term, the same in prose, tables and figure labels.
- Characters as subjects and actions as verbs: "the router benches the deployment".
- Explain why only when the claims say why.

## Figures

`@figure <kind> id=<id> title="<what it shows, as a sentence>"`, then pipe rows, then an optional
`@steps <figure-id>` block. The reader site draws, lays out and animates figures; the story gives
structure only. Every label is plain words, at most 5 words; steps are plain sentences with chips.

| Kind | Rows | Use for |
| --- | --- | --- |
| `flow` | `\| node <id> \| <label> \| <claims> \|`, `\| <a> > <b> \| <label> \| <claims> \|` | gates and branches in order; a label ending in `?` is a decision |
| `states` | `\| state <id> \| <label> \| <claims> \|`, `\| <a> > <b> \| <trigger> \| <claims> \|` | the lifecycle of one thing |
| `sequence` | `\| actor <id> \| <label> \|`, `\| <a> > <b> \| <message> \| <claims> \|` in order | hops between parties over time |
| `timeline` | `\| lane <id> \| <label> \|`, `\| <time> \| <lane> \| <what happens> \| <state after> \| <claims> \|` | **an example played out over time**: the title starts with "Example:", times are the example's own clock (`0s`, `1.5s`, `2 min`), every event and state is cited |

- *At most 12 nodes per figure; edges and messages cite claims; steps target a node id or `a>b`.
- Give each module one example timeline for its central mechanism: concrete deployments, real
  values from the claims, what happens second by second. People learn rules from worked examples.
- Draw what a sentence cannot carry. If a figure only names boxes the prose lists, cut it.

## System story (`_meta/story/_system.md`)

```md
---
module: _system
---
# The router sends every AI request to a healthy provider and retries elsewhere when one fails
@plain
(the whole system in 50 to 130 plain words: what it is for, who uses it, what it protects against)
## Words you'll see
(the system's key terms: model group, deployment, cooldown, fallback, ...)
## What happens when a request succeeds
(one or two plain paragraphs) then:
@path flow-async-chat-completion-that-succeeds
| 1 | The caller asks the router for a model group, such as "gpt-4o" [RSETUP-186]. |
| 2 | ... |
```
One section per main path of the overview, each with an `@path <flow-id>` block giving every step of
that path in plain words, numbered as the overview numbers them (G8 checks the ids and counts). The
reader site shows these steps in the walkthrough, with the overview's exact wording behind an
Expert switch. Add a section on what can go wrong for the business (outages, cost, security
exposure) citing the suspected defects, and a figure where one helps. Watch out lists the top risks.

## Gate G8: `check_story.py <specs> [--module NAME]`

Errors cover everything marked * above, plus: unknown claim IDs, a missing headline, plain words or
minute, a missing At-a-glance table where required, figures over 12 nodes or with malformed rows,
steps that target nothing, a timeline whose events go back in time or whose title does not start with
"Example:", and a system story missing a path or with the wrong number of steps. Warnings: headings
that read as labels, passive voice over 15%, grade level over 10, a story citing none of the module's
suspected defects, length outside 700 to 1,800 words (3,000 for the system story).

Which blocks belong to which layer is defined once, in `check_story.block_layer`: the site tags each
block with it and the persona snapshot (`story_probe.py --lens everyone`) prints exactly the Everyone
blocks, so a persona reader is tested on what an Everyone reader sees (L77).

`site_data.py` compiles a story that passes; one that fails is left out, with the gate's errors in
`_meta/story/<name>.check.json`, so the site never shows an unchecked story.
