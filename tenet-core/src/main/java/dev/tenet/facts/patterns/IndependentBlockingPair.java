package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record IndependentBlockingPair(
    String firstCall, SourceRef firstSite, String secondCall, SourceRef secondSite) {

  public IndependentBlockingPair {
    Objects.requireNonNull(firstCall, "firstCall");
    Objects.requireNonNull(firstSite, "firstSite");
    Objects.requireNonNull(secondCall, "secondCall");
    Objects.requireNonNull(secondSite, "secondSite");
  }
}
