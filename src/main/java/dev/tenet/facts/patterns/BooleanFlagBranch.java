package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record BooleanFlagBranch(String paramName, SourceRef site) {

  public BooleanFlagBranch {
    Objects.requireNonNull(paramName, "paramName");
    Objects.requireNonNull(site, "site");
  }
}
