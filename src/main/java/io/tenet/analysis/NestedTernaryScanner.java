package io.tenet.analysis;

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.ConditionalExpressionTree;
import com.sun.source.util.TreeScanner;
import io.tenet.api.MutableState;

final class NestedTernaryScanner extends TreeScanner<Void, Void> {
    @MutableState(reason = "Tracks conditional expression depth during one scan.")
    private int depth;
    @MutableState(reason = "Records whether one method contains a nested ternary.")
    private boolean found;

    @Override
    public Void visitConditionalExpression(final ConditionalExpressionTree node, final Void unused) {
        depth++;
        found |= depth > 1;
        final Void result = super.visitConditionalExpression(node, unused);
        depth--;
        return result;
    }

    @Override
    public Void visitClass(final ClassTree node, final Void unused) {
        return null;
    }

    boolean found() {
        return found;
    }
}
