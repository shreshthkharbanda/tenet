package io.tenet.analysis;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;
import io.tenet.config.TenetConfig;

import java.util.List;

record CompilationBatch(
        List<JavaSource> sources,
        ProjectFacts facts,
        JavacTask task,
        List<CompilationUnitTree> units,
        TenetConfig config) {
}
