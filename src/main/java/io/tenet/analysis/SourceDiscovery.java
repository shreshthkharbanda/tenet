package io.tenet.analysis;

import io.tenet.config.TenetConfig;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class SourceDiscovery {
    private SourceDiscovery() {
    }

    public static List<JavaSource> discover(
            final Path workingDirectory,
            final List<Path> requestedPaths,
            final TenetConfig config) throws IOException {
        final Map<Path, JavaSource> sources = new LinkedHashMap<>();
        for (final Path requestedPath : requestedPaths) {
            final Path absolutePath = workingDirectory.resolve(requestedPath).normalize().toAbsolutePath();
            if (!Files.exists(absolutePath)) {
                throw new IllegalArgumentException("Source path does not exist: " + requestedPath);
            }
            if (Files.isDirectory(absolutePath)) {
                discoverDirectory(workingDirectory, absolutePath, config, sources);
            } else if (absolutePath.toString().endsWith(".java")) {
                addSource(workingDirectory, absolutePath, config, sources);
            }
        }
        return sources.values().stream()
                .sorted((left, right) -> left.displayPath().compareTo(right.displayPath()))
                .toList();
    }

    private static void discoverDirectory(
            final Path workingDirectory,
            final Path directory,
            final TenetConfig config,
            final Map<Path, JavaSource> sources) throws IOException {
        final List<Path> candidates = new ArrayList<>();
        try (java.util.stream.Stream<Path> paths = Files.walk(directory)) {
            paths.filter(Files::isRegularFile)
                    .filter(path -> path.toString().endsWith(".java"))
                    .sorted()
                    .forEach(candidates::add);
        }
        for (final Path candidate : candidates) {
            addSource(workingDirectory, candidate, config, sources);
        }
    }

    private static void addSource(
            final Path workingDirectory,
            final Path absolutePath,
            final TenetConfig config,
            final Map<Path, JavaSource> sources) throws IOException {
        final Path normalizedWorkingDirectory = workingDirectory.normalize().toAbsolutePath();
        final Path relativePath = absolutePath.startsWith(normalizedWorkingDirectory)
                ? normalizedWorkingDirectory.relativize(absolutePath)
                : absolutePath.getFileName();
        if (config.sources().excluded(relativePath)) {
            return;
        }
        final String displayPath = relativePath.toString().replace('\\', '/');
        final String content = Files.readString(absolutePath, StandardCharsets.UTF_8);
        sources.putIfAbsent(absolutePath, new JavaSource(absolutePath, displayPath, content));
    }
}
