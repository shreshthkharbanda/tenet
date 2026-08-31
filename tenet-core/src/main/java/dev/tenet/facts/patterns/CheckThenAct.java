package dev.tenet.facts.patterns;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record CheckThenAct(String stateDisplay, String checkCall, String actCall, SourceRef site) {

  public CheckThenAct {
    Objects.requireNonNull(stateDisplay, "stateDisplay");
    Objects.requireNonNull(checkCall, "checkCall");
    Objects.requireNonNull(actCall, "actCall");
    Objects.requireNonNull(site, "site");
  }
}
