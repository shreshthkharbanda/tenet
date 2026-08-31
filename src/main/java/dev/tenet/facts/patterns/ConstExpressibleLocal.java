package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record ConstExpressibleLocal(String varName, SourceRef site) {

  public ConstExpressibleLocal {
    Objects.requireNonNull(varName, "varName");
    Objects.requireNonNull(site, "site");
  }
}
