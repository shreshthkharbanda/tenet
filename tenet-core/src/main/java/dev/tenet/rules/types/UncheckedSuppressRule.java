package dev.tenet.rules.types;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.UncheckedUse;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class UncheckedSuppressRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-D06",
          "Unchecked suppression",
          Dimension.TYPES,
          Severity.ADVISORY,
          1,
          "defensive doctrine: every unchecked suppression deserves a second look",
          "@SuppressWarnings(\"unchecked\") sites. The suppression is the JDK's sanctioned "
              + "escape hatch for generic internals, so this lives in the defensive profile, "
              + "not the default.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (UncheckedUse use : method.uncheckedUses()) {
        if (use.kind() == UncheckedUse.Kind.SUPPRESS_UNCHECKED) {
          findings.add(finding(method, use));
        }
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, UncheckedUse use) {
    return Finding.builder(DESCRIPTOR.id(), "Unchecked suppression in " + method.id().display())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(use.site())
        .witness("use", use.display())
        .suggestion("confine the cast behind a checked helper if the shape allows it")
        .certificate(new Certificate.Syntactic("unchecked suppression", use.site()))
        .build();
  }
}
