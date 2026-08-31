package dev.tenet.rules;

import dev.tenet.engine.TenetConfig;
import dev.tenet.rules.doctrine.ClassitisRule;
import dev.tenet.rules.doctrine.DeepModulesRule;
import dev.tenet.rules.doctrine.ShortMethodsRule;
import dev.tenet.rules.doctrine.SmallClassesRule;
import dev.tenet.rules.fault.RetriedNonIdempotentRule;
import dev.tenet.rules.fault.UnboundedFanOutRule;
import dev.tenet.rules.names.BooleanPredicateRule;
import dev.tenet.rules.names.VagueIdentifierRule;
import dev.tenet.rules.names.VocabularyDriftRule;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class Profiles {

  public static final String CONSENSUS = "consensus";
  public static final String CLEAN_CODE = "clean-code";
  public static final String DEEP_MODULES = "deep-modules";
  public static final String CONVENTIONS = "conventions";
  public static final String DEFENSIVE = "defensive";

  private static final Map<String, Set<String>> DOCTRINE_RULES =
      Map.of(
          CLEAN_CODE, Set.of("TNT-CC01", "TNT-CC02"),
          DEEP_MODULES, Set.of("TNT-DM01", "TNT-DM02"),
          CONVENTIONS, Set.of("TNT-A02", "TNT-A03", "TNT-A04"),
          DEFENSIVE, Set.of("TNT-H03", "TNT-H06"));

  private static final Map<String, String> CONFLICTS =
      Map.of(
          "TNT-CC01", "TNT-DM01",
          "TNT-CC02", "TNT-DM02");

  private Profiles() {}

  public static List<Rule> enabled(TenetConfig config) {
    Set<String> profiles = selectedProfiles(config);
    Set<String> profileRules = new java.util.TreeSet<>();
    for (String profile : profiles) {
      profileRules.addAll(DOCTRINE_RULES.getOrDefault(profile, Set.of()));
    }
    List<Rule> selected = new ArrayList<>();
    for (Rule rule : Rules.all(config)) {
      if (config.enabled(rule.descriptor().id())) selected.add(rule);
    }
    for (Rule rule : doctrineRules(config)) {
      String id = rule.descriptor().id();
      boolean wanted =
          (profileRules.contains(id) || config.explicitlyEnabled(id)) && config.enabled(id);
      if (wanted) selected.add(rule);
    }
    rejectConflicts(selected);
    return List.copyOf(selected);
  }

  private static Set<String> selectedProfiles(TenetConfig config) {
    Set<String> profiles = new java.util.TreeSet<>();
    for (String raw : config.profile().split(",")) {
      String profile = raw.trim();
      if (profile.isEmpty() || profile.equals(CONSENSUS)) continue;
      if (!DOCTRINE_RULES.containsKey(profile)) {
        throw new IllegalArgumentException(
            "unknown profile: "
                + profile
                + " (use consensus, clean-code, deep-modules, conventions, or defensive)");
      }
      profiles.add(profile);
    }
    return profiles;
  }

  public static List<Rule> doctrineRules(TenetConfig config) {
    return List.of(
        new ShortMethodsRule(config),
        new SmallClassesRule(config),
        new DeepModulesRule(config),
        new ClassitisRule(config),
        new BooleanPredicateRule(),
        new VagueIdentifierRule(),
        new VocabularyDriftRule(),
        new UnboundedFanOutRule(),
        new RetriedNonIdempotentRule());
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
