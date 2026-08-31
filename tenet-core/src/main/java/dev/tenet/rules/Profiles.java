package dev.tenet.rules;

import dev.tenet.engine.TenetConfig;
import dev.tenet.rules.doctrine.ClassitisRule;
import dev.tenet.rules.doctrine.DeepModulesRule;
import dev.tenet.rules.doctrine.ShortMethodsRule;
import dev.tenet.rules.doctrine.SmallClassesRule;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class Profiles {

  public static final String CONSENSUS = "consensus";
  public static final String CLEAN_CODE = "clean-code";
  public static final String DEEP_MODULES = "deep-modules";

  private static final Map<String, Set<String>> DOCTRINE_RULES =
      Map.of(
          CLEAN_CODE, Set.of("TNT-CC01", "TNT-CC02"),
          DEEP_MODULES, Set.of("TNT-DM01", "TNT-DM02"));

  private static final Map<String, String> CONFLICTS =
      Map.of(
          "TNT-CC01", "TNT-DM01",
          "TNT-CC02", "TNT-DM02");

  private Profiles() {}

  public static List<Rule> enabled(TenetConfig config) {
    String profile = config.profile();
    if (!DOCTRINE_RULES.containsKey(profile) && !profile.equals(CONSENSUS)) {
      throw new IllegalArgumentException(
          "unknown profile: " + profile + " (use consensus, clean-code, or deep-modules)");
    }
    List<Rule> selected = new ArrayList<>();
    for (Rule rule : Rules.all(config)) {
      if (config.enabled(rule.descriptor().id())) selected.add(rule);
    }
    for (Rule rule : doctrineRules(config)) {
      String id = rule.descriptor().id();
      boolean inProfile = DOCTRINE_RULES.getOrDefault(profile, Set.of()).contains(id);
      boolean wanted = (inProfile || config.explicitlyEnabled(id)) && config.enabled(id);
      if (wanted) selected.add(rule);
    }
    rejectConflicts(selected);
    return List.copyOf(selected);
  }

  public static List<Rule> doctrineRules(TenetConfig config) {
    return List.of(
        new ShortMethodsRule(config),
        new SmallClassesRule(config),
        new DeepModulesRule(config),
        new ClassitisRule(config));
  }

  private static void rejectConflicts(List<Rule> selected) {
    Set<String> ids = new java.util.TreeSet<>();
    selected.forEach(rule -> ids.add(rule.descriptor().id()));
    for (Map.Entry<String, String> conflict : CONFLICTS.entrySet()) {
      if (ids.contains(conflict.getKey()) && ids.contains(conflict.getValue())) {
        throw new IllegalArgumentException(
            conflict.getKey()
                + " and "
                + conflict.getValue()
                + " encode opposing doctrines and cannot both be enabled; pick one school"
                + " via the profile setting or per-rule config");
      }
    }
  }
}
