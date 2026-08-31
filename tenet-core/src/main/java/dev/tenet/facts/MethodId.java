package dev.tenet.facts;

import java.util.Objects;

public record MethodId(TypeName owner, String name, String signature)
    implements Comparable<MethodId> {

  public MethodId {
    Objects.requireNonNull(owner, "owner");
    Objects.requireNonNull(name, "name");
    Objects.requireNonNull(signature, "signature");
  }

  public String display() {
    return owner.simple() + "#" + name;
  }

  @Override
  public int compareTo(MethodId other) {
    int byOwner = owner.compareTo(other.owner);
    if (byOwner != 0) return byOwner;
    int byName = name.compareTo(other.name);
    return byName != 0 ? byName : signature.compareTo(other.signature);
  }

  @Override
  public String toString() {
    return owner + "#" + name + signature;
  }
}
