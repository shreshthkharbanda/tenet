package dev.tenet.rules.state;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.ConstExpressibleLocal;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class ReassignmentTheaterRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-C03",
          "Reassignment theater",
          Dimension.STATE,
          Severity.PROVEN,
          2,
          "a value has one birth",
          "A local declared blank and assigned exactly once in each arm of the immediately "
              + "following if/else — const-expressible by construction.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (ConstExpressibleLocal local : method.constExpressibleLocals()) {
        findings.add(finding(method, local));
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, ConstExpressibleLocal local) {
    return Finding.builder(DESCRIPTOR.id(), "Local " + local.varName() + " wants to be final")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(local.site())
        .witness("variable", local.varName() + " in " + method.id().display())
        .witness(
            "evidence",
            "declared blank, then assigned once in each branch of the following if/else")
        .suggestion(
            "assign once at declaration via a conditional expression or an extracted method")
        .certificate(
            new Certificate.Syntactic(
                "branch-assigned local " + local.varName() + " in " + method.id().display(),
                local.site()))
        .build();
  }
}
