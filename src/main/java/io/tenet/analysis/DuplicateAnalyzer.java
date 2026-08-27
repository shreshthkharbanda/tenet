package io.tenet.analysis;

import io.tenet.config.TenetConfig;
import io.tenet.model.RuleId;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

public final class DuplicateAnalyzer {
    private final TenetConfig config;
    private final ProjectFacts facts;

    public DuplicateAnalyzer(final TenetConfig config, final ProjectFacts facts) {
        this.config = config;
        this.facts = facts;
    }

    public void analyze() {
        final List<MethodFingerprint> methods = facts.methodFingerprints().stream()
                .sorted(Comparator.comparing(MethodFingerprint::displayName)
                        .thenComparing(method -> method.source().displayPath()))
                .toList();
        final Set<String> exactDuplicateHashes = exactDuplicates(methods);
        structuralDuplicates(methods, exactDuplicateHashes);
    }

    private Set<String> exactDuplicates(final List<MethodFingerprint> methods) {
        final int minimumCharacters = config.rules().integer("min.duplicateMethodCharacters");
        final Map<String, List<MethodFingerprint>> groups = group(
                methods.stream().filter(method -> method.bodyCharacters() >= minimumCharacters).toList(),
                MethodFingerprint::exactHash);
        final Set<String> duplicateHashes = new LinkedHashSet<>();
        for (final Map.Entry<String, List<MethodFingerprint>> entry : groups.entrySet()) {
            if (entry.getValue().size() < 2) {
                continue;
            }
            duplicateHashes.add(entry.getKey());
            emitDuplicates(entry.getValue(), RuleId.DUPLICATE_METHOD, "identical body");
        }
        return duplicateHashes;
    }

    private void structuralDuplicates(
            final List<MethodFingerprint> methods,
            final Set<String> exactDuplicateHashes) {
        final int minimumNodes = config.rules().integer("min.structuralCloneNodes");
        final List<MethodFingerprint> eligible = methods.stream()
                .filter(method -> method.structuralNodes() >= minimumNodes)
                .filter(method -> !exactDuplicateHashes.contains(method.exactHash()))
                .toList();
        final Map<String, List<MethodFingerprint>> groups = group(eligible, MethodFingerprint::structuralHash);
        for (final List<MethodFingerprint> group : groups.values()) {
            final long exactBodies = group.stream().map(MethodFingerprint::exactHash).distinct().count();
            if (group.size() > 1 && exactBodies > 1) {
                emitDuplicates(group, RuleId.STRUCTURAL_CLONE, "same control and expression structure");
            }
        }
    }

    private void emitDuplicates(
            final List<MethodFingerprint> group,
            final RuleId rule,
            final String evidence) {
        final MethodFingerprint canonical = group.get(0);
        for (int index = 1; index < group.size(); index++) {
            final MethodFingerprint duplicate = group.get(index);
            facts.add(new Violation(
                    rule,
                    duplicate.source(),
                    duplicate.location(),
                    "Method `" + duplicate.displayName() + "` duplicates `" + canonical.displayName() + "`",
                    evidence + "; canonical=" + canonical.source().displayPath() + ":" + canonical.location().line()));
        }
    }

    private static Map<String, List<MethodFingerprint>> group(
            final List<MethodFingerprint> methods,
            final Function<MethodFingerprint, String> classifier) {
        final Map<String, List<MethodFingerprint>> groups = new LinkedHashMap<>();
        for (final MethodFingerprint method : methods) {
            groups.computeIfAbsent(classifier.apply(method), ignored -> new java.util.ArrayList<>()).add(method);
        }
        return groups;
    }
}
