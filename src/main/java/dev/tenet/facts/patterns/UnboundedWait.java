package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record UnboundedWait(Kind kind, String callDisplay, SourceRef site) {

  public enum Kind {
    FUTURE_GET,
    FUTURE_JOIN
  }

  public UnboundedWait {
    Objects.requireNonNull(kind, "kind");
    Objects.requireNonNull(callDisplay, "callDisplay");
    Objects.requireNonNull(site, "site");
  }
}
