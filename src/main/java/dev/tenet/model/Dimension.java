package dev.tenet.model;

public enum Dimension {
  NAMES("A", "Names tell the truth"),
  SHAPE("B", "Methods do one thing"),
  STATE("C", "State is minimized"),
  TYPES("D", "Types tell the truth"),
  EFFECTS("E", "Errors and effects live at boundaries"),
  TRUTH("F", "One fact, one place"),
  DESIGN("G", "Design at scale"),
  FAULT("H", "Concurrency and fault tolerance");

  public final String key;
  public final String label;

  Dimension(String key, String label) {
    this.key = key;
    this.label = label;
  }
}
