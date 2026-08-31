package dev.tenet.report;

import dev.tenet.engine.Report;
import dev.tenet.model.Finding;
import java.util.Locale;
import java.util.Map;
import java.util.StringJoiner;

public final class JsonRenderer implements ReportRenderer {

  @Override
  public String render(Report report) {
    StringJoiner findings = new StringJoiner(",\n", "[\n", "\n  ]");
    for (Finding finding : report.findings()) {
      findings.add(renderFinding(finding));
    }
    return "{\n"
        + "  \"tool\": \"tenet\",\n"
        + "  \"stats\": "
        + renderStats(report)
        + ",\n"
        + "  \"findings\": "
        + (report.findings().isEmpty() ? "[]" : findings)
        + "\n"
        + "}\n";
  }

  private String renderStats(Report report) {
    Report.Stats stats = report.stats();
    return String.format(
        Locale.ROOT,
        "{\"files\": %d, \"classes\": %d, \"methods\": %d, "
            + "\"rejectedCandidates\": %d, \"suppressed\": %d, \"baselined\": %d, "
            + "\"compilationErrors\": %d, \"durationMillis\": %d}",
        stats.files(),
        stats.classes(),
        stats.methods(),
        stats.rejectedCandidates(),
        stats.suppressedFindings(),
        stats.baselinedFindings(),
        stats.compilationErrors(),
        stats.durationMillis());
  }

  private String renderFinding(Finding finding) {
    StringJoiner witness = new StringJoiner(", ", "{", "}");
    for (Map.Entry<String, String> entry : finding.witness().entrySet()) {
      witness.add(Json.quote(entry.getKey()) + ": " + Json.quote(entry.getValue()));
    }
    return "    {"
        + "\"rule\": "
        + Json.quote(finding.ruleId())
        + ", \"severity\": "
        + Json.quote(finding.severity().name())
        + ", \"dimension\": "
        + Json.quote(finding.dimension().name())
        + ", \"title\": "
        + Json.quote(finding.title())
        + ", \"file\": "
        + Json.quote(finding.file())
        + ", \"line\": "
        + finding.line()
        + ", \"witness\": "
        + witness
        + ", \"suggestion\": "
        + Json.quote(finding.suggestion())
        + "}";
  }

}
