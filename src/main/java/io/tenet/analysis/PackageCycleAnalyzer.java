package io.tenet.analysis;

import io.tenet.api.MutableState;
import io.tenet.model.RuleId;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class PackageCycleAnalyzer {
    private final ProjectFacts facts;

    public PackageCycleAnalyzer(final ProjectFacts facts) {
        this.facts = facts;
    }

    public void analyze() {
        final Map<String, String> packageByType = new LinkedHashMap<>();
        final Map<String, TypeDependencies> exampleByPackage = new LinkedHashMap<>();
        for (final TypeDependencies type : facts.typeDependencies()) {
            packageByType.put(type.sourceType(), type.sourcePackage());
            exampleByPackage.putIfAbsent(type.sourcePackage(), type);
        }
        final Map<String, Set<String>> graph = graph(packageByType);
        final List<Set<String>> components = new StronglyConnectedComponents(graph).find();
        for (final Set<String> component : components) {
            if (!isCycle(component, graph)) {
                continue;
            }
            final List<String> packages = component.stream().sorted().toList();
            final TypeDependencies example = exampleByPackage.get(packages.get(0));
            facts.add(new Violation(
                    RuleId.PACKAGE_CYCLE,
                    example.source(),
                    example.location(),
                    "Package dependency cycle contains: " + String.join(", ", packages),
                    "components=" + packages.size()));
        }
    }

    private Map<String, Set<String>> graph(final Map<String, String> packageByType) {
        final Map<String, Set<String>> graph = new LinkedHashMap<>();
        packageByType.values().forEach(packageName -> graph.putIfAbsent(packageName, new LinkedHashSet<>()));
        for (final TypeDependencies source : facts.typeDependencies()) {
            final Set<String> edges = graph.get(source.sourcePackage());
            for (final String targetType : source.targetTypes()) {
                final String targetPackage = packageByType.get(targetType);
                if (targetPackage != null && !targetPackage.equals(source.sourcePackage())) {
                    edges.add(targetPackage);
                }
            }
        }
        return graph;
    }

    private static boolean isCycle(final Set<String> component, final Map<String, Set<String>> graph) {
        if (component.size() > 1) {
            return true;
        }
        final String only = component.iterator().next();
        return graph.getOrDefault(only, Set.of()).contains(only);
    }

    private static final class StronglyConnectedComponents {
        private final Map<String, Set<String>> graph;
        private final Map<String, Integer> indexes = new LinkedHashMap<>();
        private final Map<String, Integer> lowLinks = new LinkedHashMap<>();
        private final Deque<String> stack = new ArrayDeque<>();
        private final Set<String> onStack = new LinkedHashSet<>();
        private final List<Set<String>> components = new ArrayList<>();
        @MutableState(reason = "Allocates deterministic Tarjan indexes during one traversal.")
        private int nextIndex;

        private StronglyConnectedComponents(final Map<String, Set<String>> graph) {
            this.graph = graph;
        }

        private List<Set<String>> find() {
            graph.keySet().stream().sorted().forEach(node -> {
                if (!indexes.containsKey(node)) {
                    connect(node);
                }
            });
            components.sort(Comparator.comparing(component -> component.stream().sorted().findFirst().orElse("")));
            return components;
        }

        private void connect(final String node) {
            indexes.put(node, nextIndex);
            lowLinks.put(node, nextIndex);
            nextIndex++;
            stack.push(node);
            onStack.add(node);
            graph.getOrDefault(node, Set.of()).stream().sorted().forEach(target -> inspectEdge(node, target));
            if (lowLinks.get(node).equals(indexes.get(node))) {
                extractComponent(node);
            }
        }

        private void inspectEdge(final String source, final String target) {
            if (!indexes.containsKey(target)) {
                connect(target);
                lowLinks.put(source, Math.min(lowLinks.get(source), lowLinks.get(target)));
            } else if (onStack.contains(target)) {
                lowLinks.put(source, Math.min(lowLinks.get(source), indexes.get(target)));
            }
        }

        private void extractComponent(final String root) {
            final Set<String> component = new LinkedHashSet<>();
            String node;
            do {
                node = stack.pop();
                onStack.remove(node);
                component.add(node);
            } while (!node.equals(root));
            components.add(component);
        }
    }
}
