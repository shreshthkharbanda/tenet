package dev.tenet.facts;

import java.util.Objects;
import java.util.Set;

public record SuppressionScope(String file, long startLine, long endLine, Set<String> ruleIds) {

  public SuppressionScope {
    Objects.requireNonNull(file, "file");
    ruleIds = Set.copyOf(ruleIds);
  }

  public boolean covers(String findingFile, long line, String ruleId) {
    return file.equals(findingFile)
        && line >= startLine
        && line <= endLine
        && (ruleIds.isEmpty() || ruleIds.contains(ruleId));
  }
}
