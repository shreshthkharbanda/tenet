package io.tenet.analysis;

import com.sun.source.tree.CatchTree;
import com.sun.source.tree.ImportTree;
import com.sun.source.util.TreeScanner;
import io.tenet.model.RuleId;

final class DirectRuleAnalyzer extends TreeScanner<Void, Void> {
    private final CompilationContext context;

    DirectRuleAnalyzer(final CompilationContext context) {
        this.context = context;
    }

    @Override
    public Void visitImport(final ImportTree importTree, final Void unused) {
        if (importTree.getQualifiedIdentifier().toString().endsWith(".*")) {
            context.add(
                    RuleId.WILDCARD_IMPORT,
                    importTree,
                    "Replace the wildcard import with explicit dependencies",
                    importTree.getQualifiedIdentifier().toString());
        }
        return super.visitImport(importTree, unused);
    }

    @Override
    public Void visitCatch(final CatchTree catchTree, final Void unused) {
        CatchRuleAnalyzer.analyze(catchTree, context);
        return super.visitCatch(catchTree, unused);
    }
}
