package io.tenet.analysis;

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.MemberSelectTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

final class CohesionMethodAnalyzer {
    private final Trees trees;
    private final Set<Element> fields;

    CohesionMethodAnalyzer(final Trees trees, final Set<Element> fields) {
        this.trees = trees;
        this.fields = fields;
    }

    int components(final TreePath classPath, final ClassTree type) {
        final List<MethodEntry> methods = methods(classPath, type);
        final Set<Element> methodElements = methods.stream()
                .map(MethodEntry::element)
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        final List<MethodUsage> usages = new ArrayList<>();
        for (final MethodEntry method : methods) {
            usages.add(usage(method, methodElements));
        }
        return CohesionModel.significantComponents(usages);
    }

    private List<MethodEntry> methods(final TreePath classPath, final ClassTree type) {
        final List<MethodEntry> methods = new ArrayList<>();
        for (final Tree member : type.getMembers()) {
            if (member instanceof MethodTree method && eligible(method)) {
                addMethod(classPath, method, methods);
            }
        }
        return methods;
    }

    private void addMethod(
            final TreePath classPath,
            final MethodTree method,
            final List<MethodEntry> methods) {
        final TreePath methodPath = new TreePath(classPath, method);
        final Element element = trees.getElement(methodPath);
        if (element instanceof ExecutableElement executable) {
            methods.add(new MethodEntry(methodPath, method, executable));
        }
    }

    private MethodUsage usage(final MethodEntry method, final Set<Element> methods) {
        final UsageCollector collector = new UsageCollector(trees, fields, methods);
        collector.scan(new TreePath(method.path(), method.tree().getBody()), null);
        return new MethodUsage(method.element(), collector.fields(), collector.calls());
    }

    private static boolean eligible(final MethodTree method) {
        return method.getBody() != null
                && method.getReturnType() != null
                && !method.getModifiers().getFlags().contains(Modifier.STATIC);
    }

    private record MethodEntry(TreePath path, MethodTree tree, ExecutableElement element) {
    }

    private static final class UsageCollector extends TreePathScanner<Void, Void> {
        private final Trees trees;
        private final Set<Element> knownFields;
        private final Set<Element> knownMethods;
        private final Set<Element> fields = new LinkedHashSet<>();
        private final Set<Element> calls = new LinkedHashSet<>();

        private UsageCollector(
                final Trees trees,
                final Set<Element> knownFields,
                final Set<Element> knownMethods) {
            this.trees = trees;
            this.knownFields = knownFields;
            this.knownMethods = knownMethods;
        }

        @Override
        public Void visitClass(final ClassTree node, final Void unused) {
            return null;
        }

        @Override
        public Void visitIdentifier(final IdentifierTree node, final Void unused) {
            recordField();
            return super.visitIdentifier(node, unused);
        }

        @Override
        public Void visitMemberSelect(final MemberSelectTree node, final Void unused) {
            recordField();
            return super.visitMemberSelect(node, unused);
        }

        @Override
        public Void visitMethodInvocation(final MethodInvocationTree node, final Void unused) {
            final Element element = trees.getElement(getCurrentPath());
            if (knownMethods.contains(element)) {
                calls.add(element);
            }
            return super.visitMethodInvocation(node, unused);
        }

        private void recordField() {
            final Element element = trees.getElement(getCurrentPath());
            if (knownFields.contains(element)) {
                fields.add(element);
            }
        }

        private Set<Element> fields() {
            return Set.copyOf(fields);
        }

        private Set<Element> calls() {
            return Set.copyOf(calls);
        }
    }
}
