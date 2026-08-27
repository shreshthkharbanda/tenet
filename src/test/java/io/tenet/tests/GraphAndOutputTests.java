package io.tenet.tests;

import java.io.IOException;

final class GraphAndOutputTests {
    private GraphAndOutputTests() {
    }

    static void rejectsPackageCycle() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("alpha/Alpha.java", """
                    package alpha;

                    import beta.Beta;

                    public final class Alpha {
                        private final Beta beta;

                        public Alpha(final Beta beta) {
                            this.beta = beta;
                        }

                        public Beta beta() {
                            return beta;
                        }
                    }
                    """);
            project.write("beta/Beta.java", """
                    package beta;

                    import alpha.Alpha;

                    public final class Beta {
                        private final Alpha alpha;

                        public Beta(final Alpha alpha) {
                            this.alpha = alpha;
                        }

                        public Alpha alpha() {
                            return alpha;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-PACKAGE-CYCLE");
        }
    }

    static void enforcesArchitectureBoundary() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.config("architecture.forbiddenDependencies=app.domain.** -> app.infrastructure.**\n");
            project.write("app/infrastructure/Store.java", """
                    package app.infrastructure;

                    public final class Store {
                    }
                    """);
            project.write("app/domain/Domain.java", """
                    package app.domain;

                    import app.infrastructure.Store;

                    public final class Domain {
                        private final Store store;

                        public Domain(final Store store) {
                            this.store = store;
                        }

                        public Store store() {
                            return store;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-ARCHITECTURE-BOUNDARY");
        }
    }

    static void emitsJson() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Json.java", """
                    // invalid explanation
                    public final class Json {
                    }
                    """);
            final RunResult result = project.check("--format", "json");
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "\"filesScanned\":1");
            Assertions.contains(result.output(), "\"ruleId\":\"TENET-COMMENT\"");
            Assertions.contains(result.output(), "\"severity\":\"error\"");
        }
    }

    static void emitsSarif() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Sarif.java", """
                    // invalid explanation
                    public final class Sarif {
                    }
                    """);
            final RunResult result = project.check("--format", "sarif");
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "\"version\":\"2.1.0\"");
            Assertions.contains(result.output(), "\"ruleId\":\"TENET-COMMENT\"");
            Assertions.contains(result.output(), "\"startLine\":1");
        }
    }

    static void producesStableOrdering() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("B.java", "// invalid b\npublic final class B {}\n");
            project.write("A.java", "// invalid a\npublic final class A {}\n");
            final RunResult first = project.check("--format", "json", "--fail-on", "never");
            final RunResult second = project.check("--format", "json", "--fail-on", "never");
            Assertions.exitCode(first, 0);
            Assertions.equal(first.output(), second.output());
            Assertions.ordered(first.output(), "A.java", "B.java");
        }
    }

    static void handlesCliCommands() throws IOException {
        try (final TestProject project = TestProject.create()) {
            final RunResult invalid = project.run("check", "--unknown");
            Assertions.exitCode(invalid, 2);
            Assertions.contains(invalid.error(), "Unknown option");
            final RunResult explain = project.run("explain", "TENET-COHESION");
            Assertions.exitCode(explain, 0);
            Assertions.contains(explain.output(), "one connected responsibility");
        }
    }
}
