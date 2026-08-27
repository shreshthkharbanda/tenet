package io.tenet.analysis;

import javax.lang.model.element.Element;
import java.util.LinkedHashMap;
import java.util.Map;

final class CohesionModel {
    private CohesionModel() {
    }

    static int significantComponents(final java.util.List<MethodUsage> usages) {
        final UnionFind methods = new UnionFind(usages);
        connectCalls(usages, methods);
        connectFields(usages, methods);
        final Map<Element, Integer> sizes = new LinkedHashMap<>();
        for (final MethodUsage usage : usages) {
            sizes.merge(methods.find(usage.method()), 1, Integer::sum);
        }
        return (int) sizes.values().stream().filter(size -> size >= 2).count();
    }

    private static void connectCalls(final java.util.List<MethodUsage> usages, final UnionFind methods) {
        for (final MethodUsage usage : usages) {
            for (final Element called : usage.calls()) {
                methods.union(usage.method(), called);
            }
        }
    }

    private static void connectFields(final java.util.List<MethodUsage> usages, final UnionFind methods) {
        final Map<Element, Element> firstMethodByField = new LinkedHashMap<>();
        for (final MethodUsage usage : usages) {
            for (final Element field : usage.fields()) {
                final Element first = firstMethodByField.putIfAbsent(field, usage.method());
                if (first != null) {
                    methods.union(first, usage.method());
                }
            }
        }
    }

    private static final class UnionFind {
        private final Map<Element, Element> parent = new LinkedHashMap<>();

        private UnionFind(final java.util.List<MethodUsage> usages) {
            usages.forEach(usage -> parent.put(usage.method(), usage.method()));
        }

        private Element find(final Element value) {
            final Element directParent = parent.get(value);
            if (directParent.equals(value)) {
                return value;
            }
            final Element root = find(directParent);
            parent.put(value, root);
            return root;
        }

        private void union(final Element left, final Element right) {
            if (!parent.containsKey(right)) {
                return;
            }
            final Element leftRoot = find(left);
            final Element rightRoot = find(right);
            if (!leftRoot.equals(rightRoot)) {
                parent.put(rightRoot, leftRoot);
            }
        }
    }
}
