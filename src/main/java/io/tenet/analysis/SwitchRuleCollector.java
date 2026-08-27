package io.tenet.analysis;

import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import io.tenet.model.RuleId;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;

final class SwitchRuleCollector extends TreePathScanner<Void, Void> {
    private final Trees trees;
    private final CompilationContext context;

    SwitchRuleCollector(final Trees trees, final CompilationContext context) {
        this.trees = trees;
        this.context = context;
    }

    @Override
    public Void visitSwitch(final com.sun.source.tree.SwitchTree switchTree, final Void unused) {
        collect(getCurrentPath(), switchTree.getExpression(), switchTree);
        return super.visitSwitch(switchTree, unused);
    }

    @Override
    public Void visitSwitchExpression(
            final com.sun.source.tree.SwitchExpressionTree switchTree,
            final Void unused) {
        collect(getCurrentPath(), switchTree.getExpression(), switchTree);
        return super.visitSwitchExpression(switchTree, unused);
    }

    private void collect(final TreePath switchPath, final ExpressionTree expression, final Tree switchTree) {
        final TypeMirror type = trees.getTypeMirror(new TreePath(switchPath, expression));
        if (type == null) {
            return;
        }
        if (type.toString().equals("java.lang.String")) {
            context.add(
                    RuleId.STRING_DISCRIMINATOR,
                    switchTree,
                    "Replace the string switch with an enum or sealed type",
                    "selector type=java.lang.String");
            return;
        }
        collectEnum(type, switchTree);
    }

    private void collectEnum(final TypeMirror type, final Tree switchTree) {
        if (type.getKind() != TypeKind.DECLARED) {
            return;
        }
        final Element element = ((DeclaredType) type).asElement();
        if (element.getKind() == ElementKind.ENUM) {
            context.facts().switchSites().add(new SwitchSite(
                    ((TypeElement) element).getQualifiedName().toString(),
                    context.source(),
                    Location.of(context.unit(), context.positions(), switchTree)));
        }
    }
}
