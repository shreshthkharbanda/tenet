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
            + "\"rejectedCandidates\": %d, \"compilationErrors\": %d, \"durationMillis\": %d}",
        stats.files(),
        stats.classes(),
        stats.methods(),
        stats.rejectedCandidates(),
        stats.compilationErrors(),
        stats.durationMillis());
  }

  private String renderFinding(Finding finding) {
    StringJoiner witness = new StringJoiner(", ", "{", "}");
    for (Map.Entry<String, String> entry : finding.witness().entrySet()) {
      witness.add(quote(entry.getKey()) + ": " + quote(entry.getValue()));
    }
    return "    {"
        + "\"rule\": "
        + quote(finding.ruleId())
        + ", \"severity\": "
        + quote(finding.severity().name())
        + ", \"dimension\": "
        + quote(finding.dimension().name())
        + ", \"title\": "
        + quote(finding.title())
        + ", \"file\": "
        + quote(finding.file())
        + ", \"line\": "
        + finding.line()
        + ", \"witness\": "
        + witness
        + ", \"suggestion\": "
        + quote(finding.suggestion())
        + "}";
  }

  private String quote(String raw) {
    StringBuilder escaped = new StringBuilder("\"");
    for (char c : raw.toCharArray()) {
      switch (c) {
        case '"' -> escaped.append("\\\"");
        case '\\' -> escaped.append("\\\\");
        case '\n' -> escaped.append("\\n");
        case '\r' -> escaped.append("\\r");
        case '\t' -> escaped.append("\\t");
        default -> {
          if (c < 0x20) escaped.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
          else escaped.append(c);
        }
      }
    }
    return escaped.append('"').toString();
  }
}
