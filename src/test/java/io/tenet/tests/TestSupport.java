package io.tenet.tests;

import io.tenet.cli.TenetMain;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

final class TestProject implements AutoCloseable {
    private final Path root;

    private TestProject(final Path root) {
        this.root = root;
    }

    static TestProject create() throws IOException {
        return new TestProject(Files.createTempDirectory("tenet-test-"));
    }

    void write(final String relativePath, final String content) throws IOException {
        final Path target = root.resolve(relativePath);
        Files.createDirectories(target.getParent());
        Files.writeString(target, content, StandardCharsets.UTF_8);
    }

    void config(final String content) throws IOException {
        write("tenet.properties", content);
    }

    RunResult check(final String... options) {
        final List<String> arguments = new ArrayList<>();
        arguments.add("check");
        arguments.add(".");
        arguments.addAll(List.of(options));
        return run(arguments.toArray(String[]::new));
    }

    RunResult run(final String... arguments) {
        final ByteArrayOutputStream outputBytes = new ByteArrayOutputStream();
        final ByteArrayOutputStream errorBytes = new ByteArrayOutputStream();
        final PrintStream output = new PrintStream(outputBytes, true, StandardCharsets.UTF_8);
        final PrintStream error = new PrintStream(errorBytes, true, StandardCharsets.UTF_8);
        final int exitCode = TenetMain.run(arguments, output, error, root);
        return new RunResult(
                exitCode,
                outputBytes.toString(StandardCharsets.UTF_8),
                errorBytes.toString(StandardCharsets.UTF_8));
    }

    @Override
    public void close() throws IOException {
        final List<Path> paths;
        try (var discovered = Files.walk(root)) {
            paths = discovered.sorted(Comparator.reverseOrder()).toList();
        }
        for (final Path path : paths) {
            Files.deleteIfExists(path);
        }
    }
}

record RunResult(int exitCode, String output, String error) {
}

final class Assertions {
    private Assertions() {
    }

    static void exitCode(final RunResult result, final int expected) {
        if (result.exitCode() != expected) {
            throw new AssertionError(
                    "expected exit " + expected + " but got " + result.exitCode()
                            + "\nstdout:\n" + result.output() + "\nstderr:\n" + result.error());
        }
    }

    static void contains(final String actual, final String expected) {
        if (!actual.contains(expected)) {
            throw new AssertionError("expected text to contain `" + expected + "` but was:\n" + actual);
        }
    }

    static void excludes(final String actual, final String unexpected) {
        if (actual.contains(unexpected)) {
            throw new AssertionError("expected text to exclude `" + unexpected + "` but was:\n" + actual);
        }
    }

    static void equal(final String left, final String right) {
        if (!left.equals(right)) {
            throw new AssertionError("values differ:\nleft:\n" + left + "\nright:\n" + right);
        }
    }

    static void ordered(final String actual, final String first, final String second) {
        final int firstIndex = actual.indexOf(first);
        final int secondIndex = actual.indexOf(second);
        if (firstIndex < 0 || secondIndex < 0 || firstIndex >= secondIndex) {
            throw new AssertionError("expected `" + first + "` before `" + second + "` in:\n" + actual);
        }
    }
}
