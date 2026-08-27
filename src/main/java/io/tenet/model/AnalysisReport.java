package io.tenet.model;

import java.util.List;

public record AnalysisReport(List<Finding> findings, int filesScanned) {
    public AnalysisReport {
        findings = findings.stream().sorted().toList();
    }

    public boolean rejectedBy(final FailOn failOn) {
        return findings.stream().anyMatch(finding -> failOn.rejects(finding.severity()));
    }

    public long count(final Severity severity) {
        return findings.stream().filter(finding -> finding.severity() == severity).count();
    }
}
