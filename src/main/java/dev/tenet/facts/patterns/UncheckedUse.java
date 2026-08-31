package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record UncheckedUse(Kind kind, String display, SourceRef site) {

  public enum Kind {
    RAW_TYPE,
    SUPPRESS_UNCHECKED
  }

  public UncheckedUse {
    Objects.requireNonNull(kind, "kind");
    Objects.requireNonNull(display, "display");
    Objects.requireNonNull(site, "site");
  }
}
