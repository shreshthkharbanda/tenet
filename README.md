# Tenet

**The deterministic evidence engine for Java code quality.**

Tenet finds the defects only a principal engineer's review finds today — names that lie
about effects, types that permit illegal states, retry layers that multiply, duplicated
business logic, classes that are two classes — and proves every finding with a
machine-checkable certificate before it is allowed to reach you.

No LLM in the trusted path. No configuration. No scores. Only evidence.

```
TNT-H05  PROVEN  resilientRead() retries around callUntilItWorks(), which also retries
         src/com/acme/client/RetryingClient.java:43
         callPath: RetryingClient#resilientRead -> RetryingClient#callUntilItWorks
         attemptProduct: attempts multiply across the layers (m x n)
         -> retry at exactly one layer; remove the outer loop or the inner policy
```

## Quickstart

Requires a JDK (21+) and Maven.

```bash
./bin/tenet check examples/demo        # see 43 findings on the seeded demo
./bin/tenet check path/to/your/src     # analyze your code
./bin/tenet check src --format json    # agent- and CI-consumable output
./bin/tenet rules                      # the catalog
./bin/tenet explain TNT-H05            # one rule: principle, mechanism, precision
```

Exit code `0` means clean, `1` means findings, so `tenet check` drops straight into CI.
Pass `--classpath dep.jar:dep2.jar` for dependencies; without it, unresolvable calls
degrade to UNKNOWN honestly instead of guessing.

### As an agent hook

Tenet is built to sit inside a coding agent's loop. In Claude Code, add a hook that runs
`tenet check --format json` on changed modules after edits; the JSON findings — each with
a witness and a suggestion — are structured repair instructions, not lint prose.

## What it checks

Thirty-three rules across eight dimensions of how senior engineers write:

| | Dimension | Flagship rules |
|---|---|---|
| A | Names tell the truth | Lying query (name vs. proven effect path), vocabulary drift |
| B | Methods do one thing | Boolean flag parameters, command-query violations, guard clauses |
| C | State is minimized | Ambient static state, parameter mutation |
| D | Types tell the truth | String-that-wants-to-be-an-enum (call-site evidence), boolean state machines (mutual exclusion proven), silent non-exhaustive switches |
| E | Effects live at boundaries | Swallowed failures, discarded futures, effect leaks into pure packages |
| F | One fact, one place | Duplicate logic (normalized-AST hashing), unnamed shared constants |
| G | Design at scale | Split-brain classes (LCOM4), scattered dispatch, refused bequest, pattern cosplay |
| H | Concurrency & fault tolerance | Compounding retries (call graph), sequential independent calls (def-use proof), check-then-act races, unbounded waits |

`tenet rules` lists them all; `tenet explain <id>` gives each rule's principle,
mechanism, and precision class (`PROVEN` ~0% false positives, `STRONG` <1%,
`ADVISORY` corpus-tuned).

## How it works

```
javac frontend  ->  ProgramFacts  ->  33 searchers  ->  certificate kernel  ->  findings
  (adapter)        (immutable,        (untrusted        (small, trusted:       (only what
                 compiler-free)        rules)          re-verifies every        verified)
                                                          certificate)
```

- **Certificate architecture (the de Bruijn criterion).** Rules are untrusted searchers;
  every candidate finding carries a certificate — an effect path, a call-site set, a
  cohesion partition, a reachability chain — that a small trusted kernel re-derives from
  the fact store before emission. A buggy rule can only miss, never lie.
- **Evidence over syntax.** The flagship rules need whole-program facts no single-file
  linter has: a transitive effect graph, repo-wide call-site and construction-site
  indexes, normalized body hashing, an in-repo call graph.
- **Deterministic.** Same sources, same version, byte-identical output. Sorted
  everything, no clocks, no randomness, no network.
- **Honest.** "Found" is a proof about your program. "Found nothing" is a statement
  about the search — Tenet never claims absence, and unresolvable code degrades to
  UNKNOWN instead of a guess.

## The codebase holds its own bar

`DogfoodTest` runs Tenet against Tenet's own sources and fails the build on any finding.
`ArchitectureTest` enforces the hexagonal boundary mechanically: only
`dev.tenet.frontend.javac` may import a compiler API, and the domain never depends on an
adapter. Several rules were sharpened by their own findings against this repo — the
check-then-act race the H02 rule found in the call-graph walker is fixed with the exact
`putIfAbsent` its suggestion names.

```
src/main/java/dev/tenet/
  model/      findings, severity, rule metadata          (pure domain)
  facts/      immutable program facts — compiler-free    (pure domain)
  analysis/   purity fixpoint, call graph                (pure domain)
  kernel/     certificates + the trusted verifier        (pure domain)
  rules/      33 searchers, one file per rule            (pure domain)
  engine/     ports + the application service            (pure domain)
  frontend/   the javac adapter — the only compiler code (adapter)
  report/     console + json renderers                   (adapter)
  cli/        picocli entry point                        (adapter)
```

## Development

```bash
mvn test        # unit + kernel + architecture + demo fixtures + dogfood
mvn package     # builds target/tenet.jar (used by bin/tenet)
```

Tests must stay green in this order of importance: dogfood (Tenet clean on itself),
demo fixtures (every seeded violation found, zero kernel rejections), architecture
(the dependency rule), kernel (well-formed lies rejected).
