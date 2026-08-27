package io.tenet.analysis;

import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CatchTree;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.DoWhileLoopTree;
import com.sun.source.tree.EnhancedForLoopTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.ForLoopTree;
import com.sun.source.tree.IfTree;
import com.sun.source.tree.SwitchExpressionTree;
import com.sun.source.tree.SwitchTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.WhileLoopTree;
import com.sun.source.util.TreeScanner;
import io.tenet.api.MutableState;

import java.util.List;

final class NestingDepthScanner extends TreeScanner<Void, Void> {
    @MutableState(reason = "Tracks the active control nesting during one scan.")
    private int depth;
    @MutableState(reason = "Records the maximum control nesting during one scan.")
    private int maximum;

    @Override
    public Void visitIf(final IfTree node, final Void unused) {
        scan(node.getCondition(), unused);
        scanNested(node.getThenStatement(), unused);
        scanNested(node.getElseStatement(), unused);
        return null;
    }

    @Override
    public Void visitForLoop(final ForLoopTree node, final Void unused) {
        scan(node.getInitializer(), unused);
        scan(node.getCondition(), unused);
        scan(node.getUpdate(), unused);
        scanNested(node.getStatement(), unused);
        return null;
    }

    @Override
    public Void visitEnhancedForLoop(final EnhancedForLoopTree node, final Void unused) {
        scan(node.getVariable(), unused);
        scan(node.getExpression(), unused);
        scanNested(node.getStatement(), unused);
        return null;
    }

    @Override
    public Void visitWhileLoop(final WhileLoopTree node, final Void unused) {
        scan(node.getCondition(), unused);
        scanNested(node.getStatement(), unused);
        return null;
    }

    @Override
    public Void visitDoWhileLoop(final DoWhileLoopTree node, final Void unused) {
        scanNested(node.getStatement(), unused);
        scan(node.getCondition(), unused);
        return null;
    }

    @Override
    public Void visitCatch(final CatchTree node, final Void unused) {
        scan(node.getParameter(), unused);
        scanNested(node.getBlock(), unused);
        return null;
    }

    @Override
    public Void visitSwitch(final SwitchTree node, final Void unused) {
        return scanSwitch(node.getExpression(), node.getCases(), unused);
    }

    @Override
    public Void visitSwitchExpression(final SwitchExpressionTree node, final Void unused) {
        return scanSwitch(node.getExpression(), node.getCases(), unused);
    }

    @Override
    public Void visitClass(final ClassTree node, final Void unused) {
        return null;
    }

    int maximum() {
        return maximum;
    }

    private void scanNested(final Tree tree, final Void unused) {
        if (tree == null) {
            return;
        }
        depth++;
        maximum = Math.max(maximum, depth);
        scan(tree, unused);
        depth--;
    }

    private Void scanSwitch(
            final ExpressionTree expression,
            final List<? extends CaseTree> cases,
            final Void unused) {
        scan(expression, unused);
        depth++;
        maximum = Math.max(maximum, depth);
        scan(cases, unused);
        depth--;
        return null;
    }
}
