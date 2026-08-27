package io.tenet.analysis;

import com.sun.source.tree.BinaryTree;
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CatchTree;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.ConditionalExpressionTree;
import com.sun.source.tree.DoWhileLoopTree;
import com.sun.source.tree.EnhancedForLoopTree;
import com.sun.source.tree.ForLoopTree;
import com.sun.source.tree.IfTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.WhileLoopTree;
import com.sun.source.util.TreeScanner;
import io.tenet.api.MutableState;

final class CyclomaticComplexityScanner extends TreeScanner<Void, Void> {
    @MutableState(reason = "Accumulates independent paths during one method scan.")
    private int complexity = 1;

    @Override
    public Void visitIf(final IfTree node, final Void unused) {
        complexity++;
        return super.visitIf(node, unused);
    }

    @Override
    public Void visitForLoop(final ForLoopTree node, final Void unused) {
        complexity++;
        return super.visitForLoop(node, unused);
    }

    @Override
    public Void visitEnhancedForLoop(final EnhancedForLoopTree node, final Void unused) {
        complexity++;
        return super.visitEnhancedForLoop(node, unused);
    }

    @Override
    public Void visitWhileLoop(final WhileLoopTree node, final Void unused) {
        complexity++;
        return super.visitWhileLoop(node, unused);
    }

    @Override
    public Void visitDoWhileLoop(final DoWhileLoopTree node, final Void unused) {
        complexity++;
        return super.visitDoWhileLoop(node, unused);
    }

    @Override
    public Void visitCatch(final CatchTree node, final Void unused) {
        complexity++;
        return super.visitCatch(node, unused);
    }

    @Override
    public Void visitCase(final CaseTree node, final Void unused) {
        complexity += node.getExpressions().isEmpty() ? 0 : 1;
        return super.visitCase(node, unused);
    }

    @Override
    public Void visitConditionalExpression(final ConditionalExpressionTree node, final Void unused) {
        complexity++;
        return super.visitConditionalExpression(node, unused);
    }

    @Override
    public Void visitBinary(final BinaryTree node, final Void unused) {
        final Tree.Kind kind = node.getKind();
        complexity += kind == Tree.Kind.CONDITIONAL_AND || kind == Tree.Kind.CONDITIONAL_OR ? 1 : 0;
        return super.visitBinary(node, unused);
    }

    @Override
    public Void visitClass(final ClassTree node, final Void unused) {
        return null;
    }

    int value() {
        return complexity;
    }
}
