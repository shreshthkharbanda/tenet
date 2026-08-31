package dev.tenet.facts;

public enum Visibility {
  PUBLIC,
  PROTECTED,
  PACKAGE_PRIVATE,
  PRIVATE;

  public boolean isAtLeastPackage() {
    return this != PRIVATE;
  }
}
