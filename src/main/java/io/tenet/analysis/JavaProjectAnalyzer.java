package io.tenet.analysis;

import io.tenet.config.TenetConfig;
import io.tenet.model.AnalysisReport;
import io.tenet.model.RuleId;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

public final class JavaProjectAnalyzer {
    public AnalysisReport analyze(
            final Path workingDirectory,
            final List<Path> requestedPaths,
            final TenetConfig config) throws IOException {
        final List<JavaSource> sources = SourceDiscovery.discover(workingDirectory, requestedPaths, config);
        final ProjectFacts facts = new ProjectFacts(config);
        analyzeFiles(sources, config, facts);
        if (!sources.isEmpty()) {
            new JavaCompilationAnalyzer().analyze(sources, config, facts);
        }
        finalizeProject(config, facts);
        return new AnalysisReport(List.copyOf(facts.findings()), sources.size());
    }

    private void analyzeFiles(
            final List<JavaSource> sources,
            final TenetConfig config,
            final ProjectFacts facts) {
        final int maximumLines = config.rules().integer("max.fileLines");
        for (final JavaSource source : sources) {
            new CommentScanner(source, config, facts).scan();
            final int lines = source.content().split("\\R", -1).length;
            if (lines > maximumLines) {
                facts.add(new Violation(
                        RuleId.FILE_LENGTH,
                        source,
                        new Location(1, 1),
                        "Source file contains " + lines + " lines",
                        "maximum=" + maximumLines));
            }
        }
    }

    private void finalizeProject(final TenetConfig config, final ProjectFacts facts) {
        new DuplicateAnalyzer(config, facts).analyze();
        new VariantAnalyzer(config, facts).analyze();
        new ArchitectureAnalyzer(config, facts).analyze();
        new PackageCycleAnalyzer(facts).analyze();
    }
}
