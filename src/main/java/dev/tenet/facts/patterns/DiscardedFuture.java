package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record DiscardedFuture(String callDisplay, boolean chainHandlesFailure, SourceRef site) {

  public DiscardedFuture {
    Objects.requireNonNull(callDisplay, "callDisplay");
    Objects.requireNonNull(site, "site");
  }
}
