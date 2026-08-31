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
      int compilationErrors,
      long durationMillis) {}

  public boolean clean() {
    return findings.isEmpty();
  }
}
