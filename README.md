# Tenet

Tenet is a static analyzer for Java that finds the problems a principal engineer finds in code review: methods whose names lie about their side effects, types that allow illegal states, retry layers that multiply into thundering herds, the same business logic pasted into four files. Every finding ships with machine-checked evidence. If Tenet cannot prove a claim from your code, it stays quiet.

Try it in under two minutes:

```bash
git clone https://github.com/shreshthkharbanda/tenet && cd tenet
./bin/tenet check tenet-core/examples/demo
```

The first run builds the jar (needs JDK 21+ and Maven), then prints findings from a demo project seeded with 28 kinds of planted defects. Each finding shows the rule, the file and line, the evidence, and a suggested fix:

```
TNT-H05  PROVEN  resilientRead() retries around callUntilItWorks(), which also retries
         examples/demo/src/com/acme/client/RetryingClient.java:43
         callPath: RetryingClient#resilientRead -> RetryingClient#callUntilItWorks
         attemptProduct: attempts multiply across the layers (m x n)
         -> retry at exactly one layer; remove the outer loop or the inner policy
```

## Using it

Point `check` at any source root. Analysis of a 250-file repo takes one to three seconds.

```bash
./bin/tenet check path/to/src                  # human-readable report
./bin/tenet check path/to/src --format json    # for coding agents and scripts
./bin/tenet check path/to/src --format sarif   # for GitHub code scanning
./bin/tenet rules                              # list all 34 rules
./bin/tenet explain TNT-A01                    # one rule in depth
```

If the target is a Maven project, Tenet resolves the compile classpath from the nearest `pom.xml` on its own; pass `--classpath a.jar:b.jar` only when there is no pom. Without either, calls into unresolved dependencies degrade to "unknown" and the affected rules skip rather than guess.

## Running in CI

The Maven plugin binds to `verify`, so once it is in the pom, `mvn verify` gates the build the same way Checkstyle or Spotless would:

```xml
<plugin>
  <groupId>dev.tenet</groupId>
  <artifactId>tenet-maven-plugin</artifactId>
  <version>0.1.0</version>
  <executions><execution><goals><goal>check</goal></goals></execution></executions>
</plugin>
```

The plugin reads the project's own source roots and classpath, so there is nothing else to configure. `-Dtenet.skip=true` skips a run; `-Dtenet.failOnFindings=false` reports without failing.

For GitHub, emit SARIF and upload it; findings then annotate the PR diff inline:

```yaml
- run: java -jar tenet.jar check src/main/java --format sarif > tenet.sarif
- uses: github/codeql-action/upload-sarif@v3
  with: { sarif_file: tenet.sarif }
```

This repo's own [ci.yml](.github/workflows/ci.yml) does exactly that against Tenet's sources on every push.

Two features make adoption on an existing codebase practical. `./bin/tenet baseline path/to/src` records every current finding as accepted debt in `.tenet-baseline`; from then on `check` fails only on new findings, so the ratchet only tightens. And `--changed` (optionally `--changed origin/develop`) still analyzes the whole program but reports only findings in files you touched, which is what a PR gate wants.

## Suppressing a finding

Exit code 0 means clean, 1 means findings. When a specific finding is wrong or accepted, suppress it at the class or method where it fires:

```java
@SuppressWarnings("tenet:TNT-A03")        // one rule, this scope only
public void process(String key) { ... }

@SuppressWarnings("tenet")                // every rule, this scope only
class LegacyAdapter { ... }
```

Suppressions are visible in the diff and reviewable like any other code change, which is the point: silencing a finding costs one annotation someone has to defend in review.

Every rule can be turned off or tuned. Put a `tenet.properties` at the root of the repo you are analyzing:

```properties
rules.TNT-A03.enabled=false
rules.TNT-B04.maxParams=5
```

Or override per run with `--disable TNT-A03,TNT-F02` or `--only TNT-H05`. The defaults are deliberately opinionated; the config file is the escape hatch, not the starting point.

Findings are grouped into eight dimensions, A through H: names that tell the truth, methods that do one thing, minimized state, types that make illegal states unrepresentable, failures handled at boundaries, one fact in one place, design at scale (SOLID, measured), and concurrency and fault tolerance. Severity is a precision class, not a guess about impact: PROVEN rules are mechanically decidable, STRONG rules are evidence-gated heuristics, ADVISORY rules need judgment. `tenet explain` shows the exact mechanism behind any rule.

One thing Tenet will not tell you: whether a true finding is worth fixing. A raced HashMap that only misbehaves during warmup and a raced listener registry in a class built for concurrent use produce the same rule ID with very different urgency. The witness gives you the facts; the judgment call stays yours.

## Learning from it

The interesting idea in this codebase is the trust model. Rules are untrusted searchers. A rule cannot emit a finding directly; it proposes a candidate along with a certificate, which is a small structured proof: a call chain ending in a side effect, the complete set of call sites for a parameter, a partition of a class into disconnected components. A separate kernel re-derives every certificate from the extracted program facts before anything reaches the report. A buggy rule can miss things, but it cannot lie to you. Proof assistants like Coq work this way; linters generally do not.

A reading order that follows the data:

1. `dev.tenet.facts` holds the immutable model of an analyzed program. No compiler types appear here, which is what will let other language frontends plug in later.
2. `dev.tenet.analysis` derives purity and reachability. `PurityAnalyzer` runs a two-phase fixpoint: effects that escape an object (I/O, static writes, parameter mutation) propagate through the whole call graph, while writes to an object's own fields propagate only along same-class call chains. That second phase exists because an earlier version flagged every method that used a locally built builder.
3. `dev.tenet.kernel` is the trusted core: a sealed `Certificate` interface and a `Kernel` that verifies each variant with an exhaustive switch. It is deliberately small. This is where the guarantee lives, so this is where the testing budget goes.
4. `dev.tenet.rules` has one file per rule, grouped by dimension. `LyingQueryRule` and `CompoundingRetriesRule` are good first reads: each is under a hundred lines because the facts layer already did the hard work.
5. `dev.tenet.frontend.javac` is the only package allowed to import compiler APIs. It runs javac to full attribution, then reduces the typed AST into facts. `ArchitectureTest` fails the build if compiler imports leak anywhere else.

Two tests are worth reading on their own. `DogfoodTest` runs Tenet against Tenet's own sources and fails on any finding, so the analyzer is held to its own standard on every build. It has caught real bugs here: a check-then-act race in the call-graph walker, and a parameter-mutating fixpoint that poisoned the purity results (twice, embarrassingly). `KernelTest` feeds the kernel well-formed lies, such as effect paths through methods that do not exist, and asserts they are rejected.

Known limits, so you do not have to discover them: analysis is source-only (no bytecode bodies for dependencies), reflection and dynamic dispatch widen results to "unknown" rather than being resolved, and "no findings" means the searchers found nothing, which is a weaker statement than "nothing is wrong."

## Contributing

The fastest useful contribution is adjudication: run Tenet on a Java repo you know well and report findings that are wrong or noisy, with the file and line. Four false-positive classes have already been found and fixed this way, and each one made a rule permanently sharper.

To add or change a rule:

1. Write the rule as a single class in `dev.tenet.rules.<dimension>`, implementing `Rule`. Look at a neighbor in the same package for the shape.
2. Give every finding a certificate the kernel can verify. If no existing `Certificate` variant fits, extending the kernel is part of the change, and the hard part.
3. Plant a positive case in `examples/demo` and add your rule ID to `DemoFindingsTest`. The test also asserts the kernel rejects nothing, so an unverifiable certificate fails loudly.
4. Register the rule in `Rules.java`. If it has thresholds, read them from `TenetConfig` so users can tune them.
5. Run `mvn test`. All five suites must pass, including dogfood. If your rule flags Tenet's own code, either the code gets fixed or the rule gets an exemption you can defend in the PR.

House rules: one top-level type per file, no comments (the code has to carry the explanation; if it cannot, rename until it can), no wildcard imports, and hexagonal boundaries enforced by `ArchitectureTest`. Tenet enforces most of this on itself, which makes review arguments short.

Current backlog, roughly in order of value: exempt interface-obligation methods from the cohesion and refused-bequest rules, record field initializer types so a `ConcurrentHashMap` behind a `Map`-typed field stops flagging as unsafe ambient state, and investigate the 19 certificate rejections that show up when scanning Apache Commons Lang. Open an issue before starting anything large.
