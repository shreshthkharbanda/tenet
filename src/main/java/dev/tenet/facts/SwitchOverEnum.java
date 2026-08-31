package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.List;
import java.util.Objects;

public record SwitchOverEnum(
    TypeName enumType,
    TypeName ownerClass,
    MethodId ownerMethod,
    List<String> coveredConstants,
    boolean hasDefault,
    boolean defaultThrows,
    SourceRef site) {

  public SwitchOverEnum {
    Objects.requireNonNull(enumType, "enumType");
    Objects.requireNonNull(ownerClass, "ownerClass");
    Objects.requireNonNull(ownerMethod, "ownerMethod");
    coveredConstants = List.copyOf(coveredConstants);
    Objects.requireNonNull(site, "site");
  }
}
