package dev.tenet.analysis;

import dev.tenet.facts.MethodId;
import java.util.Map;
import java.util.Objects;

public final class PurityReport {

  private final Map<MethodId, Purity> verdicts;

  PurityReport(Map<MethodId, Purity> verdicts) {
    this.verdicts = Map.copyOf(verdicts);
  }

  public Purity of(MethodId id) {
    Objects.requireNonNull(id, "id");
    return verdicts.getOrDefault(id, Purity.UNKNOWN);
  }

  public boolean isProvenImpure(MethodId id) {
    return of(id) == Purity.IMPURE_PROVEN;
  }

  public boolean isPure(MethodId id) {
    return of(id) == Purity.PURE;
  }
}
