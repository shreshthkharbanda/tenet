package dev.tenet.rules.effects;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import dev.tenet.rules.support.PackageProfiles;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class EffectLeakRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-E03",
          "Effect leak into pure core",
          Dimension.EFFECTS,
          Severity.STRONG,
          2,
          "functional core, imperative shell",
          "Package effect profiles: in a pure-majority package, the minority method that "
              + "transitively reaches an effect is flagged with its full call path.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (PackageProfiles.Profile profile : PackageProfiles.of(analysis).values()) {
      if (!profile.pureMajority()) continue;
      for (MethodFacts leak : profile.impure()) {
        finding(profile.packageName(), leak, analysis).ifPresent(findings::add);
      }
    }
    return findings;
  }

  private Optional<Finding> finding(String packageName, MethodFacts leak, Analysis analysis) {
    List<MethodId> chain = analysis.callGraph().effectChain(leak.id());
    if (chain.isEmpty()) return Optional.empty();
    String terminal =
        analysis
            .facts()
            .method(chain.get(chain.size() - 1))
            .flatMap(MethodFacts::firstProvenEffect)
            .map(effect -> effect.describe())
            .orElse("");
    List<String> displays = analysis.callGraph().effectPath(leak.id()).orElse(List.of());
    return Optional.of(
        Finding.builder(
                DESCRIPTOR.id(),
                leak.name() + "() leaks an effect into pure package " + packageName)
            .dimension(DESCRIPTOR.dimension())
            .severity(DESCRIPTOR.severity())
            .at(leak.site())
            .witness("package", packageName + " is pure-majority")
            .witness("effectPath", String.join(" -> ", displays))
            .suggestion("move the effect to the edge; pass its result into this package as data")
            .certificate(new Certificate.EffectPath(chain, terminal))
            .build());
  }
}
