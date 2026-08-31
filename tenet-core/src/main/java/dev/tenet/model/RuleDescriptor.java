package dev.tenet.model;

import java.util.Objects;

public record RuleDescriptor(
    String id,
    String name,
    Dimension dimension,
    Severity severity,
    int wave,
    String principle,
    String mechanism) {

  public RuleDescriptor {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(name, "name");
    Objects.requireNonNull(dimension, "dimension");
    Objects.requireNonNull(severity, "severity");
    Objects.requireNonNull(principle, "principle");
    Objects.requireNonNull(mechanism, "mechanism");
  }
}
