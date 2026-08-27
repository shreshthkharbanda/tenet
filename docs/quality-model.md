# tenet quality model

Tenet treats source quality as a constraint system over observable program structure. It does not ask whether code appears good and it does not reduce quality to a subjective scalar.

## acceptance is a conjunction

Let (P) be the analyzed Java program, (J) the configured JDK/compiler model, and \(\theta\) the policy thresholds. Tenet accepts the program only when compilation succeeds and every enabled predicate succeeds:

$$
A(P, J, \theta) = C(P, J) \land \bigwedge_{r \in R_{enabled}} r(P, J, \theta_r)
$$

This is intentionally non-compensatory. A lower method length cannot offset a dependency cycle. An immutable object cannot offset duplicated behavior. Each invariant owns its own failure boundary.

A weighted quality score would have the form \(Q(P)=\sum_i w_iq_i(P)\). Tenet rejects that model for enforcement because different defects become exchangeable. Scores can be useful for observation; they are not sufficient for a gate.

## observable representations

Tenet derives five deterministic representations from the source set:

1. a lexical stream for comments and original source tokens;
2. attributed Java syntax trees for declarations, control flow, and expressions;
3. a symbol graph for variable writes, overrides, types, and dependencies;
4. package and method graphs for cycles and cohesion;
5. normalized method fingerprints for exact and structural duplication.

The JDK compiler is the semantic authority. The same source can resolve differently under a different Java release or classpath, so both are explicit inputs to the analysis.

## scalar bounds

### cyclomatic complexity

For structured Java source, Tenet computes:

$$
M(m) = 1 + I + L + K + S + T + B
$$

where:

- \(I\) is the number of `if` nodes;
- \(L\) is the number of `for`, enhanced `for`, `while`, and `do-while` nodes;
- \(K\) is the number of `catch` clauses;
- \(S\) is the number of non-default switch cases;
- \(T\) is the number of conditional expressions;
- \(B\) is the number of short-circuit `&&` and `||` operators.

This is the decision-count form of McCabe complexity for the structured constructs Tenet observes. Nested and local type bodies are excluded from the containing method.

The invariant is \(M(m) \leq \theta_M\) for every method \(m\).

### nesting depth

Tenet walks branch bodies, loops, catches, and switches with an integer stack depth. The metric is:

$$
D(m) = \max_{n \in control(m)} depth(n)
$$

Each alternative branch is measured independently. The invariant is \(D(m) \leq \theta_D\).

### physical budgets

Method length is the inclusive line-map span between the compiler's start and end positions. File length is the number of physical line segments in the source. These are blunt budgets, not semantic claims, so both thresholds are configurable.

### surfaces and depth

For a type \(T\):

- public API surface is the number of declared public constructors and non-overriding methods;
- interface surface is the number of declared non-constructor methods;
- fan-out is \(|Out(T)|\), the number of distinct non-platform attributed type dependencies;
- inheritance depth is the number of declared superclasses before `java.lang.Object`.

Platform packages `java.*`, `javax.*`, `jdk.*`, and `sun.*` are excluded from fan-out. This keeps the metric focused on organizational and third-party coupling rather than standard-library vocabulary.

## graph constraints

### architecture

Each attributed source-to-target type reference creates a directed edge \(T_s \rightarrow T_t\). A configured boundary is a pair of qualified-name predicates \((g_s,g_t)\). A dependency is rejected when:

$$
g_s(T_s) \land g_t(T_t)
$$

Because the graph is built from symbols, fully qualified names, implicit references, and ordinary imports have the same semantics.

### package acyclicity

Type edges are projected to package edges. Tenet runs Tarjan's strongly connected components algorithm over the directed package graph. A component is a cycle when it has more than one package, or when a singleton has a self-edge.

The invariant is that every strongly connected component has size one and no self-edge.

### cohesion

For each non-static, non-constructor method in a type, Tenet records:

- the instance fields it reads or writes;
- the methods on the same type that it invokes.

These observations form an undirected method graph. Two methods are connected when they share an instance field or one directly calls the other. Tenet computes connected components using union-find.

Singleton components are ignored to prevent one stateless operation from dominating the metric. A component with at least two methods is significant. The responsibility count is:

$$
R(T) = |\{c \in components(T) : |c| \geq 2\}|
$$

The invariant is \(R(T) \leq \theta_R\). This is an operational LCOM4-style constraint, not a claim to infer business responsibilities.

### centralized variants

Every switch whose selector resolves to enum type \(E\) creates a branch-site record. Tenet requires:

$$
sites(E) \leq \theta_V
$$

This turns repeated type tests into a measurable pressure to move behavior behind one dispatch point. String switches are separately rejected because their variant set is not represented in the type system.

## mutation constraints

Tenet associates declarations and write expressions through compiler symbols. Assignments, compound assignments, and increment/decrement operations count as writes.

A local, parameter, or catch parameter with no write after declaration must carry `final`. A field must carry `final` unless it carries `@MutableState` with a validated reason sentence. This does not prove deep immutability: arrays, collections, and referenced objects can still mutate. The assertion is specifically about rebinding and declared object state.

## duplication constraints

Exact method duplication uses SHA-256 over the compiler tree's canonical body string after a minimum character threshold.

Structural duplication walks a method body and records syntax-node kinds plus literal value types. Identifier names and literal values are deliberately omitted. The resulting sequence is hashed with SHA-256 after a minimum node threshold.

For eligible methods \(m_1\) and \(m_2\):

$$
Exact(m_1,m_2) \iff H(body(m_1)) = H(body(m_2))
$$

$$
Clone(m_1,m_2) \iff H(shape(m_1)) = H(shape(m_2)) \land H(body(m_1)) \neq H(body(m_2))
$$

The size thresholds prevent trivial getters and conventional one-line operations from becoming noise.

## lexical constraints

The comment scanner is a finite-state machine with normal, string, character, and text-block states. Comment delimiters inside literals are ignored. In normal state:

- `/*` always creates a violation;
- `//` must match the complete configured context pattern;
- accepted context records are counted per file and bounded.

This is lexical, deterministic, and independent of formatting.

## guarantee classes

| class | examples | guarantee boundary |
|---|---|---|
| compiler fact | compilation, symbol writes, selector types, dependency edges | exact relative to the configured JDK, release, source set, and classpath |
| graph invariant | package cycles, declared architecture boundaries | exact over the graph Tenet constructs |
| syntax invariant | comments, wildcard imports, nested ternaries, empty catches | exact over supported Java syntax |
| bounded metric | complexity, length, fan-out, API size, depth | measurement is exact; the chosen threshold is policy |
| structural proxy | cohesion, structural clones, centralized branching | deterministic evidence for design pressure, not proof of business intent |

Tenet labels every result with the rule and concrete evidence rather than calling a heuristic a proof.

## determinism requirements

Every rule must satisfy these implementation constraints:

1. no model inference, network request, wall-clock input, randomness, or repository history;
2. stable traversal and sorting order;
3. a versioned rule ID;
4. explicit configuration inputs;
5. source location and measured evidence;
6. positive, negative, boundary, and counterexample fixtures;
7. byte-stable machine-readable output for identical inputs.

## adding a rule

A proposed rule enters the default gate only after its author supplies:

1. the observable program representation;
2. the predicate or equation;
3. the configuration and default threshold;
4. known soundness and completeness boundaries;
5. examples that must pass;
6. examples that must fail;
7. an explanation of likely false-positive domains;
8. regression coverage through the public CLI.

This protocol is how abstract guidance becomes enforceable engineering policy without introducing an LLM judgment step.
