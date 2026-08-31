package dev.tenet.rules.state;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.DirectEffect;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class ParameterMutationRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-C02",
          "Parameter mutation",
          Dimension.STATE,
          Severity.STRONG,
          1,
          "inputs are read-only",
          "A write to a parameter's fields or collection contents in a non-private method; "
              + "private scope-local helpers are not judged in v1.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (!method.visibility().isAtLeastPackage()) continue;
      if (dev.tenet.rules.support.Names.startsWithCommandVerb(method.name())) continue;
      method.effects().stream()
          .filter(e -> e.kind() == DirectEffect.Kind.PARAM_MUTATION)
          .forEach(effect -> findings.add(finding(method, effect)));
    }
    return findings;
  }

  private Finding finding(MethodFacts method, DirectEffect effect) {
    return Finding.builder(DESCRIPTOR.id(), method.name() + "() mutates its argument")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(effect.site())
        .witness("effect", effect.describe())
        .suggestion("return a new value instead, or move the operation onto the mutated type")
        .certificate(new Certificate.EffectPath(List.of(method.id()), effect.describe()))
        .build();
  }
}
