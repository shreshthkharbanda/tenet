package io.tenet.output;

import io.tenet.model.AnalysisReport;
import io.tenet.model.Finding;
import io.tenet.model.Severity;

public final class JsonFormatter implements ReportFormatter {
    @Override
    public String format(final AnalysisReport report) {
        final StringBuilder output = new StringBuilder();
        output.append("{\"filesScanned\":").append(report.filesScanned())
                .append(",\"errors\":").append(report.count(Severity.ERROR))
                .append(",\"warnings\":").append(report.count(Severity.WARNING))
                .append(",\"findings\":[");
        for (int index = 0; index < report.findings().size(); index++) {
            if (index > 0) {
                output.append(',');
            }
            appendFinding(output, report.findings().get(index));
        }
        return output.append("]}\n").toString();
    }

    private static void appendFinding(final StringBuilder output, final Finding finding) {
        output.append("{\"ruleId\":").append(Json.quote(finding.rule().externalId()))
                .append(",\"severity\":").append(Json.quote(finding.severity().name().toLowerCase()))
                .append(",\"file\":").append(Json.quote(finding.file()))
                .append(",\"line\":").append(finding.line())
                .append(",\"column\":").append(finding.column())
                .append(",\"message\":").append(Json.quote(finding.message()))
                .append(",\"evidence\":").append(Json.quote(finding.evidence()))
                .append('}');
    }
}

