package io.tenet.model;

import java.util.Arrays;

public enum RuleId {
    COMPILATION("Source must compile before quality can be asserted", Severity.ERROR),
    COMMENT("Comments are forbidden except one-line context records", Severity.ERROR),
    WILDCARD_IMPORT("Wildcard imports hide the dependency surface", Severity.ERROR),
    FILE_LENGTH("Source files must stay within a reviewable budget", Severity.WARNING),
    CYCLOMATIC_COMPLEXITY("Independent control-flow paths must stay bounded", Severity.ERROR),
    NESTING_DEPTH("Nested control flow must stay shallow", Severity.ERROR),
    METHOD_LENGTH("Methods must stay within a verification budget", Severity.ERROR),
    PARAMETER_COUNT("Method input surfaces must stay small", Severity.ERROR),
    BOOLEAN_PARAMETER("Boolean parameters hide two distinct operations", Severity.WARNING),
    FINAL_LOCAL("Locals that never change must be final", Severity.ERROR),
    VAR_USAGE("Local types must be explicit", Severity.WARNING),
    MUTABLE_FIELD("Object state must be immutable after construction", Severity.ERROR),
    PUBLIC_FIELD("Public fields expose representation", Severity.ERROR),
    PUBLIC_API_SURFACE("Public type surfaces must stay small", Severity.WARNING),
    INTERFACE_SURFACE("Interfaces must stay client-specific", Severity.ERROR),
    TYPE_FAN_OUT("Types must limit outgoing dependencies", Severity.WARNING),
    INHERITANCE_DEPTH("Inheritance chains must stay shallow", Severity.WARNING),
    EMPTY_CATCH("Caught failures must not disappear", Severity.ERROR),
    GENERIC_EXCEPTION("Generic exception types destroy failure contracts", Severity.ERROR),
    NESTED_TERNARY("Nested conditional expressions obscure control flow", Severity.ERROR),
    STRING_DISCRIMINATOR("Closed variants must use types instead of strings", Severity.ERROR),
    VARIANT_BRANCHING("Variant behavior must have one dispatch location", Severity.WARNING),
    DUPLICATE_METHOD("One behavior must have one implementation", Severity.ERROR),
    STRUCTURAL_CLONE("Parallel method structures indicate repeated behavior", Severity.WARNING),
    PACKAGE_CYCLE("Packages must form an acyclic dependency graph", Severity.ERROR),
    ARCHITECTURE_BOUNDARY("Dependencies must respect declared boundaries", Severity.ERROR),
    COHESION("Types must contain one connected responsibility", Severity.WARNING);

    private final String principle;
    private final Severity defaultSeverity;

    RuleId(final String principle, final Severity defaultSeverity) {
        this.principle = principle;
        this.defaultSeverity = defaultSeverity;
    }

    public String externalId() {
        return "TENET-" + name().replace('_', '-');
    }

    public String principle() {
        return principle;
    }

    public Severity defaultSeverity() {
        return defaultSeverity;
    }

    public static RuleId parse(final String value) {
        final String normalized = value.trim().toUpperCase().replace("TENET-", "").replace('-', '_');
        return Arrays.stream(values())
                .filter(rule -> rule.name().equals(normalized))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unknown rule: " + value));
    }
}
