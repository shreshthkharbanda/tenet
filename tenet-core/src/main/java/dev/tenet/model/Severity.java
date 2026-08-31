package dev.tenet.model;

public enum Severity {
  PROVEN,
  STRONG,
  ADVISORY;

  public String label() {
    return switch (this) {
      case PROVEN -> "ERROR";
      case STRONG -> "WARN";
      case ADVISORY -> "SUGGEST";
    };
  }

  public boolean failsBuild() {
    return this == PROVEN;
  }
}
