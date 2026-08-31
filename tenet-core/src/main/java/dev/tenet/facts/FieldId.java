package dev.tenet.facts;

import java.util.Objects;

public record FieldId(TypeName owner, String name) implements Comparable<FieldId> {

  public FieldId {
    Objects.requireNonNull(owner, "owner");
    Objects.requireNonNull(name, "name");
  }

  @Override
  public int compareTo(FieldId other) {
    int byOwner = owner.compareTo(other.owner);
    return byOwner != 0 ? byOwner : name.compareTo(other.name);
  }

  @Override
  public String toString() {
    return owner.simple() + "." + name;
  }
}
