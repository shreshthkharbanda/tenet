package dev.tenet.report;

import dev.tenet.engine.Report;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import java.util.List;
import java.util.Map;
import java.util.StringJoiner;

public final class SarifRenderer implements ReportRenderer {

  private final List<RuleDescriptor> catalog;

  public SarifRenderer(List<RuleDescriptor> catalog) {
    this.catalog = List.copyOf(catalog);
  }

  @Override
  public String render(Report report) {
    return "{\n"
        + "  \"$schema\": \"https://json.schemastore.org/sarif-2.1.0.json\",\n"
        + "  \"version\": \"2.1.0\",\n"
        + "  \"runs\": [{\n"
        + "    \"tool\": {\"driver\": {\n"
        + "      \"name\": \"tenet\",\n"
        + "      \"informationUri\": \"https://github.com/shreshthkharbanda/tenet\",\n"
        + "      \"rules\": " + renderCatalog() + "\n"
        + "    }},\n"
        + "    \"results\": " + renderResults(report) + "\n"
        + "  }]\n"
        + "}\n";
  }

  private String renderCatalog() {
    StringJoiner rules = new StringJoiner(", ", "[", "]");
    for (RuleDescriptor descriptor : catalog) {
      rules.add("{"
          + "\"id\": " + Json.quote(descriptor.id())
          + ", \"name\": " + Json.quote(descriptor.name())
          + ", \"shortDescription\": {\"text\": " + Json.quote(descriptor.principle()) + "}"
          + ", \"fullDescription\": {\"text\": " + Json.quote(descriptor.mechanism()) + "}"
          + "}");
    }
    return rules.toString();
  }

  private String renderResults(Report report) {
    if (report.findings().isEmpty()) return "[]";
    StringJoiner results = new StringJoiner(",\n      ", "[\n      ", "\n    ]");
    for (Finding finding : report.findings()) {
      results.add(renderResult(finding));
    }
    return results.toString();
  }

  private String renderResult(Finding finding) {
    return "{"
        + "\"ruleId\": " + Json.quote(finding.ruleId())
        + ", \"level\": " + Json.quote(levelOf(finding))
        + ", \"message\": {\"text\": " + Json.quote(messageOf(finding)) + "}"
        + ", \"locations\": [{\"physicalLocation\": {"
        + "\"artifactLocation\": {\"uri\": " + Json.quote(normalize(finding.file())) + "}"
        + ", \"region\": {\"startLine\": " + Math.max(1, finding.line()) + "}"
        + "}}]"
        + "}";
  }

  private String levelOf(Finding finding) {
    return switch (finding.severity()) {
      case PROVEN -> "error";
      case STRONG -> "warning";
      case ADVISORY -> "note";
    };
  }

  private String messageOf(Finding finding) {
    StringBuilder message = new StringBuilder(finding.title());
    for (Map.Entry<String, String> entry : finding.witness().entrySet()) {
      message.append("\n").append(entry.getKey()).append(": ").append(entry.getValue());
    }
    if (!finding.suggestion().isBlank()) {
      message.append("\nfix: ").append(finding.suggestion());
    }
    return message.toString();
  }

  private String normalize(String file) {
    String stripped = file.startsWith("./") ? file.substring(2) : file;
    return stripped.replace('\\', '/');
  }
}
