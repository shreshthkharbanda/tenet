package io.tenet.analysis;

import io.tenet.config.ArchitectureBoundary;
import io.tenet.config.TenetConfig;
import io.tenet.model.RuleId;

public final class ArchitectureAnalyzer {
    private final TenetConfig config;
    private final ProjectFacts facts;

    public ArchitectureAnalyzer(final TenetConfig config, final ProjectFacts facts) {
        this.config = config;
        this.facts = facts;
    }

    public void analyze() {
        for (final TypeDependencies type : facts.typeDependencies()) {
            for (final String target : type.targetTypes()) {
                analyzeDependency(type, target);
            }
        }
    }

    private void analyzeDependency(final TypeDependencies type, final String target) {
        for (final ArchitectureBoundary boundary : config.architecture().boundaries()) {
            if (boundary.rejects(type.sourceType(), target)) {
                facts.add(new Violation(
                        RuleId.ARCHITECTURE_BOUNDARY,
                        type.source(),
                        type.location(),
                        "`" + type.sourceType() + "` must not depend on `" + target + "`",
                        boundary.sourceExpression() + " -> " + boundary.targetExpression()));
            }
        }
    }
}
