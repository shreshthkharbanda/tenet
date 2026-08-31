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

public final class TypeLaunderingRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-D05",
          "Type-system laundering",
          Dimension.TYPES,
          Severity.PROVEN,
          1,
          "the compiler stays hired",
          "Raw-type uses and @SuppressWarnings(\"unchecked\") sites, recorded at extraction.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (UncheckedUse use : method.uncheckedUses()) {
        findings.add(finding(method, use));
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, UncheckedUse use) {
    String label =
        switch (use.kind()) {
          case RAW_TYPE -> "Raw type " + use.display();
          case SUPPRESS_UNCHECKED -> "@SuppressWarnings(\"unchecked\")";
        };
    return Finding.builder(DESCRIPTOR.id(), label + " in " + method.id().display())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(use.site())
        .witness("use", use.display())
        .suggestion(
            switch (use.kind()) {
              case RAW_TYPE -> "parameterize the type; raw types erase every guarantee generics bought";
              case SUPPRESS_UNCHECKED -> "confine the cast behind a checked helper, or restructure to avoid it";
            })
        .certificate(new Certificate.Syntactic(label, use.site()))
        .build();
  }
}
