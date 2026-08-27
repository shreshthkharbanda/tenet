package io.tenet.output;

import io.tenet.model.AnalysisReport;
import io.tenet.model.Finding;
import io.tenet.model.RuleId;

import java.util.Arrays;

public final class SarifFormatter implements ReportFormatter {
    @Override
    public String format(final AnalysisReport report) {
        final StringBuilder output = new StringBuilder();
        output.append("{\"version\":\"2.1.0\",\"$schema\":")
                .append(Json.quote("https://json.schemastore.org/sarif-2.1.0.json"))
                .append(",\"runs\":[{\"tool\":{\"driver\":{\"name\":\"tenet\",\"version\":\"0.1.0\",\"rules\":[");
        appendRules(output);
        output.append("]}},\"results\":[");
        for (int index = 0; index < report.findings().size(); index++) {
            if (index > 0) {
                output.append(',');
            }
            appendFinding(output, report.findings().get(index));
        }
        return output.append("]}]}\n").toString();
    }

    private static void appendRules(final StringBuilder output) {
        final RuleId[] rules = RuleId.values();
        Arrays.sort(rules, (left, right) -> left.externalId().compareTo(right.externalId()));
        for (int index = 0; index < rules.length; index++) {
            if (index > 0) {
                output.append(',');
            }
            final RuleId rule = rules[index];
            output.append("{\"id\":").append(Json.quote(rule.externalId()))
                    .append(",\"shortDescription\":{\"text\":").append(Json.quote(rule.principle())).append("}}");
        }
    }

    private static void appendFinding(final StringBuilder output, final Finding finding) {
        output.append("{\"ruleId\":").append(Json.quote(finding.rule().externalId()))
                .append(",\"level\":").append(Json.quote(finding.severity().name().toLowerCase()))
                .append(",\"message\":{\"text\":").append(Json.quote(finding.message())).append("}")
                .append(",\"locations\":[{\"physicalLocation\":{\"artifactLocation\":{\"uri\":")
                .append(Json.quote(finding.file()))
                .append("},\"region\":{\"startLine\":").append(finding.line())
                .append(",\"startColumn\":").append(finding.column()).append("}}}]}");
    }
}

