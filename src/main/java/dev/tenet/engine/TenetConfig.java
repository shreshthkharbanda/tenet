package dev.tenet.engine;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Properties;
import java.util.Set;

public final class TenetConfig {

  private final Map<String, String> values;
  private final Set<String> disabled;
  private final Set<String> only;

  private TenetConfig(Map<String, String> values, Set<String> disabled, Set<String> only) {
    this.values = Map.copyOf(values);
    this.disabled = Set.copyOf(disabled);
    this.only = Set.copyOf(only);
  }

  public static TenetConfig defaults() {
    return new TenetConfig(Map.of(), Set.of(), Set.of());
  }

  public static TenetConfig fromProperties(Properties properties) {
    Map<String, String> values = new LinkedHashMap<>();
    for (String name : properties.stringPropertyNames()) {
      values.put(name, properties.getProperty(name).trim());
    }
    return new TenetConfig(values, Set.of(), Set.of());
  }

  public TenetConfig withDisabled(Set<String> ruleIds) {
    Set<String> merged = new LinkedHashSet<>(disabled);
    merged.addAll(ruleIds);
    return new TenetConfig(values, merged, only);
  }

  public TenetConfig withOnly(Set<String> ruleIds) {
    return new TenetConfig(values, disabled, ruleIds);
  }

  public boolean enabled(String ruleId) {
    if (!only.isEmpty()) return only.contains(ruleId);
    if (disabled.contains(ruleId)) return false;
    return !"false".equalsIgnoreCase(values.get(key(ruleId, "enabled")));
  }

  public int intParam(String ruleId, String name, int fallback) {
    String raw = values.get(key(ruleId, name));
    if (raw == null) return fallback;
    try {
      return Integer.parseInt(raw);
    } catch (NumberFormatException e) {
      throw new IllegalArgumentException(
          "config " + key(ruleId, name) + " is not an integer: " + raw, e);
    }
  }

  public double doubleParam(String ruleId, String name, double fallback) {
    String raw = values.get(key(ruleId, name));
    if (raw == null) return fallback;
    try {
      return Double.parseDouble(raw);
    } catch (NumberFormatException e) {
      throw new IllegalArgumentException(
          "config " + key(ruleId, name) + " is not a number: " + raw, e);
    }
  }

  private String key(String ruleId, String name) {
    return "rules." + ruleId + "." + name;
  }
}
