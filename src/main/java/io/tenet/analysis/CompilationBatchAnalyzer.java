package io.tenet.analysis;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.Trees;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

final class CompilationBatchAnalyzer {
    void analyze(final CompilationBatch batch) {
        final Trees trees = Trees.instance(batch.task());
        final Map<Path, JavaSource> sourcesByPath = indexSources(batch);
        for (final CompilationUnitTree unit : batch.units()) {
            analyzeUnit(batch, trees, sourcesByPath, unit);
        }
    }

    private Map<Path, JavaSource> indexSources(final CompilationBatch batch) {
        final Map<Path, JavaSource> sourcesByPath = new LinkedHashMap<>();
        batch.sources().forEach(source -> sourcesByPath.put(source.absolutePath().normalize(), source));
        return sourcesByPath;
    }

    private void analyzeUnit(
            final CompilationBatch batch,
            final Trees trees,
            final Map<Path, JavaSource> sourcesByPath,
            final CompilationUnitTree unit) {
        final Path unitPath = Path.of(unit.getSourceFile().toUri()).normalize();
        final JavaSource source = sourcesByPath.get(unitPath);
        if (source == null) {
            return;
        }
        final CompilationContext context = new CompilationContext(
                batch.config(),
                source,
                unit,
                trees.getSourcePositions(),
                batch.facts());
        new CompilationUnitAnalyzer(trees, batch.task().getElements(), context).scan(unit, null);
        new DirectRuleAnalyzer(context).scan(unit, null);
        new SwitchRuleCollector(trees, context).scan(unit, null);
    }
}
