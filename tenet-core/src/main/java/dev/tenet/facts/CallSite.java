package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public record CallSite(MethodId target, MethodId caller, List<Argument> arguments, SourceRef site) {

  public record Argument(Optional<String> literal) {
    public Argument {
      Objects.requireNonNull(literal, "literal");
    }

    public static Argument ofLiteral(String value) {
      return new Argument(Optional.of(value));
    }

    public static Argument nonLiteral() {
      return new Argument(Optional.empty());
    }
  }

  public CallSite {
    Objects.requireNonNull(target, "target");
    Objects.requireNonNull(caller, "caller");
    arguments = List.copyOf(arguments);
    Objects.requireNonNull(site, "site");
  }
}
