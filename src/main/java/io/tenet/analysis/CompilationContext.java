package io.tenet.analysis;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.SourcePositions;
import io.tenet.config.TenetConfig;
import io.tenet.model.RuleId;

public record CompilationContext(
        TenetConfig config,
        JavaSource source,
        CompilationUnitTree unit,
        SourcePositions positions,
        ProjectFacts facts) {

    public void add(final RuleId rule, final Tree tree, final String message, final String evidence) {
        facts.add(new Violation(rule, source, Location.of(unit, positions, tree), message, evidence));
    }

    public String sourceText(final Tree tree) {
        final long start = positions.getStartPosition(unit, tree);
        final long end = positions.getEndPosition(unit, tree);
        if (start < 0 || end < start || end > source.content().length()) {
            return tree.toString();
        }
        return source.content().substring((int) start, (int) end);
    }

    public int lineSpan(final Tree tree) {
        final long start = positions.getStartPosition(unit, tree);
        final long end = positions.getEndPosition(unit, tree);
        if (start < 0 || end < start || unit.getLineMap() == null) {
            return 0;
        }
        final long first = unit.getLineMap().getLineNumber(start);
        final long last = unit.getLineMap().getLineNumber(Math.max(start, end - 1));
        return Math.toIntExact(last - first + 1);
    }
}
