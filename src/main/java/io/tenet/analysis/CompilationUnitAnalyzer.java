package io.tenet.analysis;

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.Elements;
import java.util.ArrayDeque;
import java.util.Deque;

final class CompilationUnitAnalyzer extends TreePathScanner<Void, Void> {
    private final Trees trees;
    private final TypeRuleAnalyzer typeRules;
    private final MethodRuleAnalyzer methodRules;
    private final Deque<TypeElement> owners = new ArrayDeque<>();

    CompilationUnitAnalyzer(final Trees trees, final Elements elements, final CompilationContext context) {
        this.trees = trees;
        typeRules = new TypeRuleAnalyzer(trees, elements, context);
        methodRules = new MethodRuleAnalyzer(trees, context);
    }

    @Override
    public Void visitClass(final ClassTree type, final Void unused) {
        final TreePath classPath = getCurrentPath();
        final Element element = trees.getElement(classPath);
        if (!(element instanceof TypeElement typeElement)) {
            return super.visitClass(type, unused);
        }
        typeRules.analyze(classPath, type, typeElement);
        owners.push(typeElement);
        final Void result = super.visitClass(type, unused);
        owners.pop();
        return result;
    }

    @Override
    public Void visitMethod(final MethodTree method, final Void unused) {
        if (!owners.isEmpty()) {
            methodRules.analyze(getCurrentPath(), method, owners.peek());
        }
        return super.visitMethod(method, unused);
    }
}
