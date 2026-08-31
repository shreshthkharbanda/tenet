package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record ExternalCall(TypeName owner, String method, EffectClass effectClass, SourceRef site) {

  public enum EffectClass {
    PURE,
    IO,
    LOGGING,
    LOCAL_MUTATION,
    UNKNOWN
  }

  public ExternalCall {
    Objects.requireNonNull(owner, "owner");
    Objects.requireNonNull(method, "method");
    Objects.requireNonNull(effectClass, "effectClass");
    Objects.requireNonNull(site, "site");
  }

  public String display() {
    return owner.simple() + "." + method;
  }
}
