package dev.tenet.rules.shape;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.DirectEffect;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import dev.tenet.rules.support.Names;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class CommandQueryRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-B02",
          "Command-query violation",
          Dimension.SHAPE,
          Severity.STRONG,
          1,
          "commands act; queries answer; no method does both silently",
          "Returns a computed value AND carries a proven state write, under a name that admits "
              + "neither; fluent builders and conventional command verbs exempt.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (!violates(method)) continue;
      stateWrite(method).ifPresent(effect -> findings.add(finding(method, effect)));
    }
    return findings;
  }

  private boolean violates(MethodFacts method) {
    return method.returnsValue()
        && !method.returnsThis()
        && !method.isConstructor()
        && method.visibility().isAtLeastPackage()
        && !Names.startsWithCommandVerb(method.name())
        && !Names.startsWithQueryVerb(method.name());
  }

  private Optional<DirectEffect> stateWrite(MethodFacts method) {
    return method.effects().stream()
        .filter(
            e ->
                switch (e.kind()) {
                  case WRITE_INSTANCE, WRITE_STATIC, PARAM_MUTATION -> true;
                  case IO_CALL, LOG_CALL, UNKNOWN_EXTERNAL -> false;
                })
        .findFirst();
  }

  private Finding finding(MethodFacts method, DirectEffect effect) {
    return Finding.builder(DESCRIPTOR.id(), method.name() + "() returns a value and mutates state")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(effect.site())
        .witness("returns", method.returnType().simple())
        .witness("hiddenEffect", effect.describe())
        .suggestion("split into a command (void) and a query, or name the method for the effect")
        .certificate(new Certificate.EffectPath(List.of(method.id()), effect.describe()))
        .build();
  }
}
