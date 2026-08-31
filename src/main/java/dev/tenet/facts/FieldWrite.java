package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record FieldWrite(FieldId field, SourceRef site) {

  public FieldWrite {
    Objects.requireNonNull(field, "field");
    Objects.requireNonNull(site, "site");
  }
}
