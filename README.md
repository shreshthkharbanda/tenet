# tenet

Tenet is a deterministic Java quality gate. It turns strict engineering principles into compiler-backed assertions with stable evidence, no model calls, and no network dependency.

The goal is to remove mechanical design review from pull requests. Tenet rejects code that is too complex, too coupled, mutable without an explicit reason, duplicated, cyclic, weakly typed, comment-dependent, or structurally incohesive before a human sees it.

Tenet does not produce a compensating quality score. A short method cannot cancel a package cycle, and a cohesive type cannot cancel an empty catch block. A build passes only when every enabled constraint passes.

## quick start

Tenet requires a JDK 17 or newer and Bash.

```bash
./scripts/build.sh
./tenet check src/main/java
```

Run the complete repository gate:

```bash
./scripts/verify.sh
```

This compiles Tenet, runs 36 end-to-end deterministic tests, and then requires Tenet to report zero findings against its own production source.

## commands

```text
tenet check [paths...] [options]
tenet explain <rule-id>
tenet version
```

`check` accepts files, directories, or both. With no path it analyzes the current directory.

```bash
./tenet check src/main/java src/test/java
./tenet check src/main/java --format json
./tenet check src/main/java --format sarif > tenet.sarif
./tenet check src/main/java --classpath build/classes --release 17
./tenet explain TENET-COHESION
```

Exit codes are stable:

| code | meaning |
|---:|---|
| `0` | no finding reaches the configured failure threshold |
| `1` | the quality gate rejected the source |
| `2` | configuration, invocation, I/O, or JDK setup failed |

## enforced rules

All checks operate on lexical tokens, attributed compiler trees, symbols, or explicit graphs.

| rule | default | deterministic assertion |
|---|---|---|
| `TENET-COMPILATION` | error | every analyzed source must parse and resolve under the configured release and classpath |
| `TENET-COMMENT` | error | block and Javadoc comments are forbidden; at most one formatted context record is allowed per file |
| `TENET-WILDCARD-IMPORT` | error | imports must identify dependencies explicitly |
| `TENET-FILE-LENGTH` | warning | physical source lines must not exceed the file budget |
| `TENET-CYCLOMATIC-COMPLEXITY` | error | independent control-flow decisions must not exceed the configured bound |
| `TENET-NESTING-DEPTH` | error | control-flow nesting must remain shallow |
| `TENET-METHOD-LENGTH` | error | a method's physical line span must remain bounded |
| `TENET-PARAMETER-COUNT` | error | method and constructor input surfaces must remain narrow |
| `TENET-BOOLEAN-PARAMETER` | warning | boolean inputs must become named types or separate operations |
| `TENET-FINAL-LOCAL` | error | parameters, catch parameters, and locals with no later write must be `final` |
| `TENET-VAR-USAGE` | warning | local types must be explicit rather than `var` |
| `TENET-MUTABLE-FIELD` | error | fields must be `final` unless mutable state has a validated reason |
| `TENET-PUBLIC-FIELD` | error | public representation is forbidden except compile-time constants |
| `TENET-PUBLIC-API-SURFACE` | warning | declared public operations, including constructors, must stay within budget |
| `TENET-INTERFACE-SURFACE` | error | interfaces must stay client-specific |
| `TENET-TYPE-FAN-OUT` | warning | outgoing non-platform type dependencies must stay bounded |
| `TENET-INHERITANCE-DEPTH` | warning | inheritance depth must stay bounded |
| `TENET-EMPTY-CATCH` | error | caught failures must be resolved, translated, or propagated |
| `TENET-GENERIC-EXCEPTION` | error | `Exception` and `Throwable` must not define failure contracts |
| `TENET-NESTED-TERNARY` | error | conditional expressions must not contain conditional expressions |
| `TENET-STRING-DISCRIMINATOR` | error | closed variants must use an enum or sealed type rather than string switches |
| `TENET-VARIANT-BRANCHING` | warning | branching on one enum must be centralized to a bounded number of sites |
| `TENET-DUPLICATE-METHOD` | error | sufficiently large identical method bodies are forbidden |
| `TENET-STRUCTURAL-CLONE` | warning | sufficiently large methods with the same normalized syntax structure are forbidden |
| `TENET-PACKAGE-CYCLE` | error | the package dependency graph must be acyclic |
| `TENET-ARCHITECTURE-BOUNDARY` | error | attributed type dependencies must respect configured source-to-target prohibitions |
| `TENET-COHESION` | warning | a type must not contain multiple significant disconnected method/field clusters |

The formal definitions, equations, and proof boundaries are in [the quality model](docs/quality-model.md).

## zero-comment policy

Ordinary line comments, block comments, and Javadoc are rejected. Code should carry names, types, boundaries, and behavior directly.

One exception is available when external context genuinely cannot be represented in Java. A file may contain at most one line matching this complete shape:

```java
// context: External wire protocol requires this exact token.
```

The reason must start with an alphanumeric character, contain 9 to 99 characters before its final period, and fit on one line. A context record is not a lint suppression.

## explicit mutable state

State is immutable by default. A field that must change during a bounded lifecycle needs Tenet's source-retained annotation and a reason sentence:

```java
@MutableState(reason = "Advances through the immutable token stream during parsing.")
private int cursor;
```

The reason follows the same 9-to-99-character sentence constraint. The annotation permits only the field's mutability; every other rule still applies.

## configuration

Tenet loads `tenet.properties` from the working directory by default. CLI values override the file.

```properties
failOn=WARNING
java.release=17
java.classpath=
exclude=**/build/**,**/target/**,**/generated/**,**/.gradle/**
comment.contextPattern=^// context: [A-Za-z0-9].{8,98}\\.$
comment.maxPerFile=1
max.fileLines=400
max.cyclomaticComplexity=8
max.nestingDepth=3
max.methodLines=30
max.parameters=4
max.publicMethods=7
max.interfaceMethods=5
max.typeFanOut=20
max.inheritanceDepth=2
max.variantBranchSites=1
max.responsibilityComponents=1
min.duplicateMethodCharacters=80
min.structuralCloneNodes=30
architecture.forbiddenDependencies=
```

`failOn` accepts `ERROR`, `WARNING`, or `NEVER`. A rule can be promoted, demoted, or disabled with its stable external ID:

```properties
rule.TENET-COHESION.severity=error
rule.TENET-STRUCTURAL-CLONE.severity=off
```

The strict defaults are deliberate. Teams can tune measurable budgets, but broad inline suppression is not supported.

### architecture boundaries

Forbidden dependencies are semicolon-separated `source -> target` qualified-name globs:

```properties
architecture.forbiddenDependencies=\
  com.acme.domain.** -> org.springframework.**;\
  com.acme.api.** -> com.acme.infrastructure.**
```

`*` matches within one qualified-name segment. `**` crosses segments. The check uses compiler-resolved type symbols, not import text.

### source exclusions

Path exclusions are comma-separated globs. `*` stays within one path segment and `**` crosses directories. A leading `**/` also matches the project root, so `**/generated/**` excludes both `generated/X.java` and `module/generated/X.java`.

## output contracts

Text is intended for terminals. JSON is intended for scripts and contains counts plus sorted findings. SARIF 2.1.0 is intended for code-scanning systems.

Every finding includes:

- a stable rule ID;
- severity;
- normalized source path;
- line and column;
- a concrete message;
- the measured or structural evidence.

Findings are sorted by file, location, rule ID, and message. Identical source, configuration, JDK, and classpath produce byte-for-byte identical JSON and SARIF.

## continuous integration

The repository includes a GitHub Actions quality gate:

```yaml
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: "17"
- run: ./scripts/verify.sh
```

For another repository, copy the built JAR or invoke Tenet from a pinned checkout:

```bash
java -jar build/tenet.jar check src/main/java --format sarif
```

Tenet has no runtime dependencies outside the JDK.

## what the gate can and cannot prove

Tenet can deterministically enforce structural constraints that are observable in source and compiler symbols. It can prevent a large class of review churn: drifting style, hidden mutability, oversized units, repeated structures, dependency violations, cycles, and several common abstraction failures.

It does not prove business correctness, concurrency safety, security, performance, API semantics, or behavioral substitutability. Those require executable specifications, tests, contracts, threat models, and workload evidence. The near-zero-review path is therefore Tenet plus strong behavioral verification—not a claim that static structure alone proves the program correct.

## development

```bash
./scripts/build.sh
./scripts/test.sh
./scripts/verify.sh
```

The implementation uses the JDK compiler API directly. There are no parser libraries, model providers, telemetry calls, or network calls. New rules must define a measurable observable, stable evidence, a deterministic threshold or predicate, and regression fixtures before entering the default gate.

Licensed under Apache-2.0.
