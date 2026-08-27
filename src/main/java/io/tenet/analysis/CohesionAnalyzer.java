package io.tenet.analysis;

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.Trees;
import io.tenet.model.RuleId;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.Modifier;
import java.util.LinkedHashSet;
import java.util.Set;

public final class CohesionAnalyzer {
    private final Trees trees;
    private final CompilationContext context;

    public CohesionAnalyzer(final Trees trees, final CompilationContext context) {
        this.trees = trees;
        this.context = context;
    }

    public void analyze(final TreePath classPath, final ClassTree type) {
        final Set<Element> fields = fields(classPath, type);
        if (fields.size() < 2) {
            return;
        }
        final int components = new CohesionMethodAnalyzer(trees, fields).components(classPath, type);
        final int maximum = context.config().rules().integer("max.responsibilityComponents");
        if (components > maximum) {
            context.add(
                    RuleId.COHESION,
                    type,
                    "Type contains " + components + " disconnected responsibility clusters",
                    "maximum=" + maximum + "; split fields and their methods into cohesive types");
        }
    }

    private Set<Element> fields(final TreePath classPath, final ClassTree type) {
        final Set<Element> fields = new LinkedHashSet<>();
        for (final Tree member : type.getMembers()) {
            if (member instanceof VariableTree variable
                    && !variable.getModifiers().getFlags().contains(Modifier.STATIC)) {
                addField(classPath, variable, fields);
            }
        }
        return fields;
    }

    private void addField(
            final TreePath classPath,
            final VariableTree variable,
            final Set<Element> fields) {
        final Element element = trees.getElement(new TreePath(classPath, variable));
        if (element != null && element.getKind() == ElementKind.FIELD) {
            fields.add(element);
        }
    }
}
