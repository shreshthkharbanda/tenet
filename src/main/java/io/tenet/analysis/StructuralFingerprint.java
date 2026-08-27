package io.tenet.analysis;

import com.sun.source.tree.LiteralTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.TreeScanner;
import io.tenet.api.MutableState;

public final class StructuralFingerprint extends TreeScanner<Void, StringBuilder> {
    @MutableState(reason = "Counts syntax nodes while creating one fingerprint.")
    private int nodes;

    public Result calculate(final Tree tree) {
        final StringBuilder structure = new StringBuilder();
        scan(tree, structure);
        return new Result(Hashing.sha256(structure.toString()), nodes);
    }

    @Override
    public Void scan(final Tree tree, final StringBuilder structure) {
        if (tree == null) {
            structure.append("NULL;");
            return null;
        }
        nodes++;
        structure.append(tree.getKind().name()).append(';');
        return super.scan(tree, structure);
    }

    @Override
    public Void visitLiteral(final LiteralTree node, final StringBuilder structure) {
        final Object value = node.getValue();
        structure.append(value == null ? "null" : value.getClass().getSimpleName()).append(';');
        return super.visitLiteral(node, structure);
    }

    public record Result(String hash, int nodes) {
    }
}
