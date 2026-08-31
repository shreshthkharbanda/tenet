package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record CatchFact(
    String caughtType,
    Disposal disposal,
    boolean catchesInterrupted,
    boolean reinterrupts,
    SourceRef site) {

  public enum Disposal {
    EMPTY,
    LOG_ONLY,
    RETURNS_DEFAULT,
    RETHROWS,
    HANDLES
  }

  public CatchFact {
    Objects.requireNonNull(caughtType, "caughtType");
    Objects.requireNonNull(disposal, "disposal");
    Objects.requireNonNull(site, "site");
  }

  public boolean swallows() {
    return switch (disposal) {
      case EMPTY, LOG_ONLY, RETURNS_DEFAULT -> true;
      case RETHROWS, HANDLES -> false;
    };
  }
}
