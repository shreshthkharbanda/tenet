package io.tenet.analysis;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;
import io.tenet.config.TenetConfig;

import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

final class JavaCompilationAnalyzer {
    void analyze(
            final List<JavaSource> sources,
            final TenetConfig config,
            final ProjectFacts facts) throws IOException {
        final JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("tenet requires a JDK because the compiler API is unavailable");
        }
        final DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager fileManager = compiler.getStandardFileManager(diagnostics, Locale.ROOT, null)) {
            compile(new CompilerSession(sources, config, facts, compiler, diagnostics, fileManager));
        }
        CompilerDiagnosticAnalyzer.add(sources, facts, diagnostics.getDiagnostics());
    }

    private void compile(final CompilerSession session) throws IOException {
        final List<Path> paths = session.sources().stream().map(JavaSource::absolutePath).toList();
        final Iterable<? extends JavaFileObject> files = session.fileManager().getJavaFileObjectsFromPaths(paths);
        final JavacTask task = (JavacTask) session.compiler().getTask(
                null,
                session.fileManager(),
                session.diagnostics(),
                compilerOptions(session.config()),
                null,
                files);
        final List<CompilationUnitTree> units = new ArrayList<>();
        task.parse().forEach(units::add);
        task.analyze();
        new CompilationBatchAnalyzer().analyze(new CompilationBatch(
                session.sources(), session.facts(), task, units, session.config()));
    }

    private List<String> compilerOptions(final TenetConfig config) {
        final List<String> options = new ArrayList<>(List.of(
                "-proc:none",
                "--release",
                Integer.toString(config.compiler().sourceRelease()),
                "-Xlint:none"));
        if (!config.compiler().classpath().isBlank()) {
            options.add("-classpath");
            options.add(config.compiler().classpath());
        }
        return options;
    }

    private record CompilerSession(
            List<JavaSource> sources,
            TenetConfig config,
            ProjectFacts facts,
            JavaCompiler compiler,
            DiagnosticCollector<JavaFileObject> diagnostics,
            StandardJavaFileManager fileManager) {
    }
}
