package io.tenet.tests;

import java.io.IOException;

final class CommentAndCompilerTests {
    private CommentAndCompilerTests() {
    }

    static void acceptsCleanSource() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Clean.java", """
                    public final class Clean {
                        private final String value;

                        public Clean(final String value) {
                            this.value = value;
                        }

                        public String value() {
                            return value;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 0);
            Assertions.contains(result.output(), "0 errors; 0 warnings");
        }
    }

    static void rejectsOrdinaryComment() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Ordinary.java", """
                    public final class Ordinary {
                        // this explanation belongs in code
                        public int value() {
                            return 1;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-COMMENT");
        }
    }

    static void acceptsOneContextRecord() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Context.java", """
                    public final class Context {
                        // context: External wire protocol requires this exact token.
                        private static final String TOKEN = "fixed";

                        public String token() {
                            return TOKEN;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 0);
            Assertions.excludes(result.output(), "TENET-COMMENT");
        }
    }

    static void rejectsSecondContextRecord() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Contexts.java", """
                    public final class Contexts {
                        // context: External wire protocol requires this exact token.
                        private static final String FIRST = "first";
                        // context: External wire protocol requires this second token.
                        private static final String SECOND = "second";
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "context comments=2");
        }
    }

    static void ignoresCommentMarkersInLiterals() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Literals.java", """
                    public final class Literals {
                        private static final String LINE = "// not a comment";
                        private static final String BLOCK = "/* not a comment */";

                        public String value() {
                            return LINE + BLOCK;
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 0);
            Assertions.excludes(result.output(), "TENET-COMMENT");
        }
    }

    static void rejectsBlockComment() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Block.java", """
                    /* forbidden block */
                    public final class Block {
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-COMMENT");
        }
    }

    static void reportsCompilationFailure() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Broken.java", "public final class Broken {\n");
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-COMPILATION");
        }
    }

    static void rejectsWildcardImport() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Imports.java", """
                    import java.util.*;

                    public final class Imports {
                        public List<String> values() {
                            return List.of();
                        }
                    }
                    """);
            final RunResult result = project.check();
            Assertions.exitCode(result, 1);
            Assertions.contains(result.output(), "TENET-WILDCARD-IMPORT");
        }
    }

    static void excludesGeneratedSourceAtProjectRoot() throws IOException {
        try (final TestProject project = TestProject.create()) {
            project.write("Clean.java", "public final class Clean {}\n");
            project.write("generated/Broken.java", "public final class Broken {\n");
            final RunResult result = project.check();
            Assertions.exitCode(result, 0);
            Assertions.contains(result.output(), "scanned 1 Java files");
        }
    }
}
