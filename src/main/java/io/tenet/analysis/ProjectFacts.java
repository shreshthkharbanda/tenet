package io.tenet.analysis;

import io.tenet.config.TenetConfig;
import io.tenet.model.Finding;
import io.tenet.model.RuleId;
import io.tenet.model.Severity;

import java.util.ArrayList;
import java.util.List;

final class ProjectFacts {
    private final TenetConfig config;
    private final List<Finding> findings = new ArrayList<>();
    private final List<MethodFingerprint> methodFingerprints = new ArrayList<>();
    private final List<SwitchSite> switchSites = new ArrayList<>();
    private final List<TypeDependencies> typeDependencies = new ArrayList<>();

    ProjectFacts(final TenetConfig config) {
        this.config = config;
    }

    void add(final Violation violation) {
        final Severity severity = config.rules().severity(violation.rule());
        if (severity != null) {
            findings.add(new Finding(
                    violation.rule(),
                    severity,
                    violation.source().displayPath(),
                    violation.location().line(),
                    violation.location().column(),
                    violation.message(),
                    violation.evidence()));
        }
    }

    List<Finding> findings() {
        return findings;
    }

    List<MethodFingerprint> methodFingerprints() {
        return methodFingerprints;
    }

    List<SwitchSite> switchSites() {
        return switchSites;
    }

    List<TypeDependencies> typeDependencies() {
        return typeDependencies;
    }
}
