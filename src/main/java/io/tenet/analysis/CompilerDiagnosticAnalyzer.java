package io.tenet.analysis;

import io.tenet.model.RuleId;

import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class CompilerDiagnosticAnalyzer {
    private CompilerDiagnosticAnalyzer() {
    }

    static void add(
            final List<JavaSource> sources,
            final ProjectFacts facts,
            final List<Diagnostic<? extends JavaFileObject>> diagnostics) {
        final Map<Path, JavaSource> sourcesByPath = new LinkedHashMap<>();
        sources.forEach(source -> sourcesByPath.put(source.absolutePath().normalize(), source));
        diagnostics.stream()
                .filter(diagnostic -> diagnostic.getKind() == Diagnostic.Kind.ERROR)
                .forEach(diagnostic -> addDiagnostic(sources, sourcesByPath, facts, diagnostic));
    }

    private static void addDiagnostic(
            final List<JavaSource> sources,
            final Map<Path, JavaSource> sourcesByPath,
            final ProjectFacts facts,
            final Diagnostic<? extends JavaFileObject> diagnostic) {
        final JavaSource source = sourceFor(sources, sourcesByPath, diagnostic);
        facts.add(new Violation(
                RuleId.COMPILATION,
                source,
                new Location(Math.max(1, diagnostic.getLineNumber()), Math.max(1, diagnostic.getColumnNumber())),
                diagnostic.getMessage(Locale.ROOT),
                "compiler diagnostic"));
    }

    private static JavaSource sourceFor(
            final List<JavaSource> sources,
            final Map<Path, JavaSource> sourcesByPath,
            final Diagnostic<? extends JavaFileObject> diagnostic) {
        if (diagnostic.getSource() == null) {
            return sources.get(0);
        }
        final Path path = Path.of(diagnostic.getSource().toUri()).normalize();
        return sourcesByPath.getOrDefault(path, sources.get(0));
    }
}
