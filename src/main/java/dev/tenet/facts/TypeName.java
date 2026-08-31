package dev.tenet.facts;

import java.util.Objects;

public record TypeName(String qualified) implements Comparable<TypeName> {

  public TypeName {
    Objects.requireNonNull(qualified, "qualified");
  }

  public String simple() {
    int lastDot = qualified.lastIndexOf('.');
    return lastDot < 0 ? qualified : qualified.substring(lastDot + 1);
  }

  public String packageName() {
    int lastDot = qualified.lastIndexOf('.');
    return lastDot < 0 ? "" : qualified.substring(0, lastDot);
  }

  @Override
  public int compareTo(TypeName other) {
    return qualified.compareTo(other.qualified);
  }

  @Override
  public String toString() {
    return qualified;
  }
}
