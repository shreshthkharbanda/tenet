package io.tenet.analysis;

import com.sun.source.tree.AssignmentTree;
import com.sun.source.tree.CompoundAssignmentTree;
import com.sun.source.tree.LambdaExpressionTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.UnaryTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import io.tenet.model.RuleId;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.Modifier;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class LocalVariableAnalyzer extends TreePathScanner<Void, Void> {
    private final Trees trees;
    private final CompilationContext context;
    private final Map<Element, VariableTree> candidates = new LinkedHashMap<>();
    private final Set<Element> writes = new LinkedHashSet<>();

    public LocalVariableAnalyzer(final Trees trees, final CompilationContext context) {
        this.trees = trees;
        this.context = context;
    }

    public void analyze(final TreePath methodPath, final MethodTree method, final ParameterPolicy parameterPolicy) {
        if (parameterPolicy == ParameterPolicy.INCLUDE) {
            for (final VariableTree parameter : method.getParameters()) {
                addCandidate(new TreePath(methodPath, parameter), parameter);
            }
        }
        if (method.getBody() != null) {
            scan(new TreePath(methodPath, method.getBody()), null);
        }
        for (final Map.Entry<Element, VariableTree> entry : candidates.entrySet()) {
            if (!writes.contains(entry.getKey())) {
                context.add(
                        RuleId.FINAL_LOCAL,
                        entry.getValue(),
                        "Variable `" + entry.getValue().getName() + "` never changes and must be final",
                        "add the final modifier");
            }
        }
    }

    @Override
    public Void visitVariable(final VariableTree node, final Void unused) {
        addCandidate(getCurrentPath(), node);
        if (usesInferredType(node)) {
            context.add(
                    RuleId.VAR_USAGE,
                    node,
                    "Replace `var` with the explicit local type",
                    "inferred types hide the local contract");
        }
        return super.visitVariable(node, unused);
    }

    @Override
    public Void visitAssignment(final AssignmentTree node, final Void unused) {
        recordWrite(new TreePath(getCurrentPath(), node.getVariable()));
        return super.visitAssignment(node, unused);
    }

    @Override
    public Void visitCompoundAssignment(final CompoundAssignmentTree node, final Void unused) {
        recordWrite(new TreePath(getCurrentPath(), node.getVariable()));
        return super.visitCompoundAssignment(node, unused);
    }

    @Override
    public Void visitUnary(final UnaryTree node, final Void unused) {
        if (isMutation(node.getKind())) {
            recordWrite(new TreePath(getCurrentPath(), node.getExpression()));
        }
        return super.visitUnary(node, unused);
    }

    @Override
    public Void visitLambdaExpression(final LambdaExpressionTree node, final Void unused) {
        scan(node.getBody(), unused);
        return null;
    }

    private void addCandidate(final TreePath path, final VariableTree variable) {
        final Element element = trees.getElement(path);
        if (element == null || !candidateKind(element.getKind()) || element.getModifiers().contains(Modifier.FINAL)) {
            return;
        }
        candidates.putIfAbsent(element, variable);
    }

    private void recordWrite(final TreePath targetPath) {
        final Element element = trees.getElement(targetPath);
        if (element != null) {
            writes.add(element);
        }
    }

    private boolean usesInferredType(final VariableTree variable) {
        final String declaration = context.sourceText(variable);
        final String pattern = "\\bvar\\s+" + Pattern.quote(variable.getName().toString()) + "\\b";
        return Pattern.compile(pattern).matcher(declaration).find();
    }

    private static boolean candidateKind(final ElementKind kind) {
        return kind == ElementKind.LOCAL_VARIABLE
                || kind == ElementKind.PARAMETER
                || kind == ElementKind.EXCEPTION_PARAMETER;
    }

    private static boolean isMutation(final Tree.Kind kind) {
        return kind == Tree.Kind.PREFIX_INCREMENT
                || kind == Tree.Kind.PREFIX_DECREMENT
                || kind == Tree.Kind.POSTFIX_INCREMENT
                || kind == Tree.Kind.POSTFIX_DECREMENT;
    }
}
