package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.Objects;

public record DirectEffect(Kind kind, String description, SourceRef site) {

  public enum Kind {
    WRITE_INSTANCE,
    WRITE_STATIC,
    PARAM_MUTATION,
    IO_CALL,
    LOG_CALL,
    UNKNOWN_EXTERNAL
  }

  public DirectEffect {
    Objects.requireNonNull(kind, "kind");
    Objects.requireNonNull(description, "description");
    Objects.requireNonNull(site, "site");
  }

  public boolean proven() {
    return switch (kind) {
      case WRITE_INSTANCE, WRITE_STATIC, PARAM_MUTATION, IO_CALL -> true;
      case LOG_CALL, UNKNOWN_EXTERNAL -> false;
    };
  }

  public boolean escapesReceiver() {
    return switch (kind) {
      case WRITE_STATIC, PARAM_MUTATION, IO_CALL -> true;
      case WRITE_INSTANCE, LOG_CALL, UNKNOWN_EXTERNAL -> false;
    };
  }

  public boolean writeShaped(java.util.function.Predicate<String> readsAsQuery) {
    return switch (kind) {
      case WRITE_INSTANCE, WRITE_STATIC, PARAM_MUTATION -> true;
      case IO_CALL -> !readsAsQuery.test(calleeName());
      case LOG_CALL, UNKNOWN_EXTERNAL -> false;
    };
  }

  private String calleeName() {
    int lastDot = description.lastIndexOf('.');
    return lastDot < 0 ? description : description.substring(lastDot + 1);
  }

  public String describe() {
    return switch (kind) {
      case WRITE_INSTANCE -> "writes field " + description + " [STATE]";
      case WRITE_STATIC -> "writes static " + description + " [STATE]";
      case PARAM_MUTATION -> "mutates parameter " + description + " [STATE]";
      case IO_CALL -> "calls " + description + " [IO]";
      case LOG_CALL -> "calls " + description + " [LOG]";
      case UNKNOWN_EXTERNAL -> "calls " + description + " [UNKNOWN]";
    };
  }
}
