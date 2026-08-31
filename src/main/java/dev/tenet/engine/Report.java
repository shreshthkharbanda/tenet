package dev.tenet.engine;

import dev.tenet.model.Finding;
import java.util.List;

public record Report(List<Finding> findings, Stats stats) {

  public Report {
    findings = List.copyOf(findings);
  }

  public record Stats(
      int files,
      int classes,
      int methods,
      int rejectedCandidates,
      int suppressedFindings,
      int baselinedFindings,
      int compilationErrors,
      long durationMillis) {

    public Stats withBaselined(int count) {
      return new Stats(
          files, classes, methods, rejectedCandidates,
          suppressedFindings, count, compilationErrors, durationMillis);
    }
  }

  public Report withFindings(List<Finding> remaining, Stats newStats) {
    return new Report(remaining, newStats);
  }

  public boolean clean() {
    return findings.isEmpty();
  }
}
