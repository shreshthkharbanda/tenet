package dev.tenet.report;

import dev.tenet.engine.Report;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.Severity;
import java.util.List;
import java.util.Map;

public final class ConsoleRenderer implements ReportRenderer {

  private static final String RESET = "[0m";
  private static final String BOLD = "[1m";
  private static final String DIM = "[2m";
  private static final String GREEN = "[32m";
  private static final String YELLOW = "[33m";
  private static final String RED = "[31m";
  private static final String CYAN = "[36m";

  private final boolean colored;

  public ConsoleRenderer(boolean colored) {
    this.colored = colored;
  }

  @Override
  public String render(Report report) {
    StringBuilder out = new StringBuilder();
    out.append(paint(BOLD, "TENET")).append(" · evidence engine for Java\n");
    appendStatsLine(out, report);
    out.append('\n');
    if (report.clean()) {
      out.append(paint(GREEN, "No findings. "))
          .append("Every rule ran; every silence is honest.\n");
      return out.toString();
    }
    appendFindings(out, report);
    appendSummary(out, report);
    return out.toString();
  }

  private void appendStatsLine(StringBuilder out, Report report) {
    Report.Stats stats = report.stats();
    out.append(
        paint(
            DIM,
            String.format(
                "analyzed %d files · %d types · %d methods · %d ms%s",
                stats.files(),
                stats.classes(),
                stats.methods(),
                stats.durationMillis(),
                stats.compilationErrors() > 0
                    ? " · "
                        + stats.compilationErrors()
                        + " compilation errors (analysis is partial)"
                    : "")));
    out.append('\n');
  }

  private void appendFindings(StringBuilder out, Report report) {
    Map<Dimension, List<Finding>> byDimension = new java.util.EnumMap<>(Dimension.class);
    for (Finding finding : report.findings()) {
      byDimension
          .computeIfAbsent(finding.dimension(), key -> new java.util.ArrayList<>())
          .add(finding);
    }
    for (Dimension dimension : Dimension.values()) {
      List<Finding> findings = byDimension.get(dimension);
      if (findings == null) continue;
      out.append(
              paint(
                  BOLD, dimension.key + " · " + dimension.label.toUpperCase(java.util.Locale.ROOT)))
          .append('\n');
      findings.forEach(finding -> appendFinding(out, finding));
      out.append('\n');
    }
  }

  private void appendFinding(StringBuilder out, Finding finding) {
    out.append("  ")
        .append(paint(CYAN, finding.ruleId()))
        .append("  ")
        .append(paint(severityColor(finding.severity()), severityLabel(finding.severity())))
        .append("  ")
        .append(paint(BOLD, finding.title()))
        .append('\n');
    out.append("           ")
        .append(paint(DIM, finding.file() + ":" + finding.line()))
        .append('\n');
    finding
        .witness()
        .forEach(
            (key, value) ->
                out.append("           ").append(key).append(": ").append(value).append('\n'));
    if (!finding.suggestion().isBlank()) {
      out.append("           ").append(paint(GREEN, "-> " + finding.suggestion())).append('\n');
    }
  }

  private void appendSummary(StringBuilder out, Report report) {
    out.append(paint(BOLD, "Summary: ")).append(report.findings().size()).append(" findings");
    if (report.stats().rejectedCandidates() > 0) {
      out.append(" · ")
          .append(report.stats().rejectedCandidates())
          .append(" candidates rejected by the kernel (searcher bugs, not shown)");
    }
    if (report.stats().suppressedFindings() > 0) {
      out.append(" · ").append(report.stats().suppressedFindings()).append(" suppressed");
    }
    if (report.stats().baselinedFindings() > 0) {
      out.append(" · ").append(report.stats().baselinedFindings()).append(" baselined");
    }
    out.append('\n');
  }

  private String severityLabel(Severity severity) {
    return switch (severity) {
      case PROVEN -> "PROVEN  ";
      case STRONG -> "STRONG  ";
      case ADVISORY -> "ADVISORY";
    };
  }

  private String severityColor(Severity severity) {
    return switch (severity) {
      case PROVEN -> RED;
      case STRONG -> YELLOW;
      case ADVISORY -> DIM;
    };
  }

  private String paint(String code, String text) {
    return colored ? code + text + RESET : text;
  }
}
