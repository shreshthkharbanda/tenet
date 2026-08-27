package io.tenet.tests;

import java.io.IOException;

final class MetricRuleTests {
    private MetricRuleTests() {
    }

    static void rejectsComplexMethod() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Complex.java", """
                    public final class Complex {
                        public int decide(final int value) {
                            if (value == 1) { return 1; }
                            if (value == 2) { return 2; }
                            if (value == 3) { return 3; }
                            if (value == 4) { return 4; }
                            if (value == 5) { return 5; }
                            if (value == 6) { return 6; }
                            if (value == 7) { return 7; }
                            if (value == 8) { return 8; }
                            return 0;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-CYCLOMATIC-COMPLEXITY");
        }
    }

    static void rejectsDeepNesting() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Nested.java", """
                    public final class Nested {
                        public int decide(final int value) {
                            if (value > 0) {
                                if (value > 1) {
                                    if (value > 2) {
                                        if (value > 3) {
                                            return value;
                                        }
                                    }
                                }
                            }
                            return 0;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-NESTING-DEPTH");
        }
    }

    static void enforcesFileAndMethodBudgets() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.config("max.fileLines=5\nmax.methodLines=2\n");
            project.write("Budgets.java", """
                    public final class Budgets {
                        public int value() {
                            return 1;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-FILE-LENGTH");
            Assertions.contains(result.output(), "TENET-METHOD-LENGTH");
        }
    }

    static void rejectsWideParameterSurface() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Parameters.java", """
                    public final class Parameters {
                        public int sum(
                                final int first,
                                final int second,
                                final int third,
                                final int fourth,
                                final int fifth) {
                            return first + second + third + fourth + fifth;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-PARAMETER-COUNT");
        }
    }

    static void rejectsBooleanParameter() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("BooleanInput.java", """
                    public final class BooleanInput {
                        public int value(final boolean enabled) {
                            return enabled ? 1 : 0;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-BOOLEAN-PARAMETER");
        }
    }

    static void requiresFinalStableLocals() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Stable.java", """
                    public final class Stable {
                        public String copy(final String value) {
                            String copy = value;
                            return copy;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-FINAL-LOCAL");
        }
    }

    static void rejectsInferredLocalType() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Inferred.java", """
                    public final class Inferred {
                        public String copy(final String value) {
                            final var copy = value;
                            return copy;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-VAR-USAGE");
        }
    }
}
