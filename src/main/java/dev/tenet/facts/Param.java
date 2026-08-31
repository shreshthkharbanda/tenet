package dev.tenet.facts;

import java.util.Objects;

public record Param(String name, TypeName type, boolean isBoolean) {

  public Param {
    Objects.requireNonNull(name, "name");
    Objects.requireNonNull(type, "type");
  }
}
