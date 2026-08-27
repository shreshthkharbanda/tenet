package io.tenet.tests;

import java.io.IOException;

final class DesignRuleTests {
    private DesignRuleTests() {
    }

    static void rejectsMutableAndPublicFields() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Fields.java", """
                    public final class Fields {
                        public final Object exposed = new Object();
                        private int mutable;
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-MUTABLE-FIELD");
            Assertions.contains(result.output(), "TENET-PUBLIC-FIELD");
        }
    }

    static void acceptsReasonedMutableState() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("State.java", """
                    import io.tenet.api.MutableState;

                    public final class State {
                        @MutableState(reason = "Tracks deterministic parser position.")
                        private int position;

                        public void advance() {
                            position++;
                        }
                    }
                    """);
            final RunResult result = project.check("--classpath", System.getProperty("java.class.path"));
            Assertions.exitCode(result, 0);
            Assertions.excludes(result.output(), "TENET-MUTABLE-FIELD");
        }
    }

    static void rejectsUnexplainedMutableState() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("State.java", """
                    import io.tenet.api.MutableState;

                    public final class State {
                        @MutableState(reason = "because")
                        private int position;
                    }
                    """);
            final RunResult result = project.check("--classpath", System.getProperty("java.class.path"));
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-MUTABLE-FIELD");
        }
    }

    static void limitsPublicSurface() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.config("max.publicMethods=1\n");
            project.write("Surface.java", """
                    public final class Surface {
                        private final String value;

                        public Surface(final String value) {
                            this.value = value;
                        }

                        public String value() {
                            return value;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-PUBLIC-API-SURFACE");
        }
    }

    static void limitsInterfaceSurface() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Wide.java", """
                    public interface Wide {
                        int first();
                        int second();
                        int third();
                        int fourth();
                        int fifth();
                        int sixth();
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-INTERFACE-SURFACE");
        }
    }

    static void limitsTypeFanOut() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.config("max.typeFanOut=0\n");
            project.write("Dependency.java", "public final class Dependency {}\n");
            project.write("Consumer.java", """
                    public final class Consumer {
                        private final Dependency dependency;

                        public Consumer(final Dependency dependency) {
                            this.dependency = dependency;
                        }

                        public Dependency dependency() {
                            return dependency;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-TYPE-FAN-OUT");
        }
    }

    static void limitsInheritanceDepth() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Deep.java", """
                    class First {}
                    class Second extends First {}
                    class Third extends Second {}
                    public final class Deep extends Third {}
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-INHERITANCE-DEPTH");
        }
    }

    static void rejectsEmptyGenericCatch() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Failures.java", """
                    public final class Failures {
                        public void run() {
                            try {
                                Integer.parseInt("x");
                            } catch (Exception failure) {
                            }
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-EMPTY-CATCH");
            Assertions.contains(result.output(), "TENET-GENERIC-EXCEPTION");
        }
    }

    static void rejectsNestedTernary() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Ternary.java", """
                    public final class Ternary {
                        public int value(final int input) {
                            return input > 0 ? input > 1 ? 2 : 1 : 0;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-NESTED-TERNARY");
        }
    }

    static void rejectsStringDiscriminator() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Strings.java", """
                    public final class Strings {
                        public int value(final String input) {
                            return switch (input) {
                                case "one" -> 1;
                                default -> 0;
                            };
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-STRING-DISCRIMINATOR");
        }
    }

    static void centralizesVariantBranching() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Variants.java", """
                    public final class Variants {
                        public int first(final Kind kind) {
                            return switch (kind) {
                                case FIRST -> 1;
                                case SECOND -> 2;
                            };
                        }

                        public String second(final Kind kind) {
                            return switch (kind) {
                                case FIRST -> "first";
                                case SECOND -> "second";
                            };
                        }
                    }

                    enum Kind {
                        FIRST,
                        SECOND
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-VARIANT-BRANCHING");
        }
    }

    static void detectsExactDuplication() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.config("min.duplicateMethodCharacters=1\n");
            project.write("Duplicates.java", """
                    public final class Duplicates {
                        public int first(final int value) {
                            return value + 1;
                        }

                        public int second(final int value) {
                            return value + 1;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-DUPLICATE-METHOD");
        }
    }

    static void detectsStructuralClone() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.config("min.structuralCloneNodes=1\n");
            project.write("Clones.java", """
                    public final class Clones {
                        public int first(final int value) {
                            return value + 1;
                        }

                        public int second(final int input) {
                            return input + 2;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-STRUCTURAL-CLONE");
        }
    }

    static void detectsDisconnectedResponsibilities() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Responsibilities.java", """
                    public final class Responsibilities {
                        private final int left;
                        private final int right;

                        public Responsibilities(final int left, final int right) {
                            this.left = left;
                            this.right = right;
                        }

                        public int left() { return left; }
                        public int nextLeft() { return left + 1; }
                        public int right() { return right; }
                        public int nextRight() { return right + 1; }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-COHESION");
        }
    }
}
