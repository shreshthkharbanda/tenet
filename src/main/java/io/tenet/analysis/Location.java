package io.tenet.analysis;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.SourcePositions;

public record Location(long line, long column) {
    public static Location of(
            final CompilationUnitTree unit,
            final SourcePositions positions,
            final Tree tree) {
        return of(unit, positions.getStartPosition(unit, tree));
    }

    public static Location of(final CompilationUnitTree unit, final long position) {
        if (position < 0 || unit.getLineMap() == null) {
            return new Location(1, 1);
        }
        return new Location(
                unit.getLineMap().getLineNumber(position),
                unit.getLineMap().getColumnNumber(position));
    }
}

