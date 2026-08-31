package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record FieldFacts(
    FieldId id,
    TypeName type,
    SourceRef site,
    Visibility visibility,
    boolean isStatic,
    boolean isFinal,
    boolean isBoolean,
    boolean isMutableCollection,
    boolean isInfraType,
    boolean hasInitializer) {

  public FieldFacts {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(type, "type");
    Objects.requireNonNull(site, "site");
    Objects.requireNonNull(visibility, "visibility");
  }
}
