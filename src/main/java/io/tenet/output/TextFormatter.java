package io.tenet.output;

import io.tenet.model.AnalysisReport;
import io.tenet.model.Finding;
import io.tenet.model.Severity;

public final class TextFormatter implements ReportFormatter {
    @Override
    public String format(final AnalysisReport report) {
        final StringBuilder output = new StringBuilder();
        for (final Finding finding : report.findings()) {
            output.append(finding.file())
                    .append(':').append(finding.line())
                    .append(':').append(finding.column())
                    .append(' ').append(finding.severity().name().toLowerCase())
                    .append(' ').append(finding.rule().externalId())
                    .append(' ').append(finding.message());
            if (!finding.evidence().isBlank()) {
                output.append(" [").append(finding.evidence()).append(']');
            }
            output.append(System.lineSeparator());
        }
        output.append("tenet: scanned ").append(report.filesScanned()).append(" Java files; ")
                .append(report.count(Severity.ERROR)).append(" errors; ")
                .append(report.count(Severity.WARNING)).append(" warnings")
                .append(System.lineSeparator());
        return output.toString();
    }
}

