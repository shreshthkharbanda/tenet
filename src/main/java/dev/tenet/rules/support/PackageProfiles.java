package dev.tenet.rules.support;

import dev.tenet.analysis.Analysis;
import dev.tenet.analysis.Purity;
import dev.tenet.facts.MethodFacts;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class PackageProfiles {

  public static final int MIN_KNOWN_METHODS = 8;
  public static final double MIN_PURE_RATIO = 0.8;

  public record Profile(
      String packageName, int knownCount, int pureCount, List<MethodFacts> impure) {
    public Profile {
      impure = List.copyOf(impure);
    }

    public boolean pureMajority() {
      return knownCount >= MIN_KNOWN_METHODS
          && !impure.isEmpty()
          && (double) pureCount / knownCount >= MIN_PURE_RATIO;
    }
  }

  private PackageProfiles() {}

  public static Map<String, Profile> of(Analysis analysis) {
    Map<String, List<MethodFacts>> byPackage = new TreeMap<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (method.isConstructor() || method.isTrivialAccessor()) continue;
      byPackage
          .computeIfAbsent(method.id().owner().packageName(), key -> new ArrayList<>())
          .add(method);
    }
    Map<String, Profile> profiles = new TreeMap<>();
    byPackage.forEach(
        (packageName, methods) ->
            profiles.put(packageName, profile(packageName, methods, analysis)));
    return profiles;
  }

  private static Profile profile(String packageName, List<MethodFacts> methods, Analysis analysis) {
    List<MethodFacts> impure = new ArrayList<>();
    int pure = 0;
    int known = 0;
    for (MethodFacts method : methods) {
      Purity verdict = analysis.purity().of(method.id());
      if (verdict == Purity.UNKNOWN) continue;
      known++;
      if (verdict == Purity.PURE) pure++;
      else impure.add(method);
    }
    return new Profile(packageName, known, pure, impure);
  }
}
