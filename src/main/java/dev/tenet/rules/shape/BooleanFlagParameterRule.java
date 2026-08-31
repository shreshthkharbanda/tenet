package dev.tenet.rules.shape;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.BooleanFlagBranch;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class BooleanFlagParameterRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-B01",
          "Boolean flag parameter",
          Dimension.SHAPE,
          Severity.PROVEN,
          1,
          "a method does one thing",
          "A boolean parameter whose only use is the condition of a top-level branch covering "
              + "the whole body — proven from the control-flow shape.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (BooleanFlagBranch branch : method.booleanFlagBranches()) {
        findings.add(finding(method, branch));
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, BooleanFlagBranch branch) {
    return Finding.builder(
            DESCRIPTOR.id(),
            method.name() + "(" + branch.paramName() + ") is two methods wearing one name")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(branch.site())
        .witness("parameter", branch.paramName())
        .witness("evidence", "its only use is the top-level branch covering the whole body")
        .suggestion(
            "split into two methods named for what each branch does; extract any shared middle")
        .certificate(
            new Certificate.Syntactic(
                "boolean flag parameter " + branch.paramName() + " in " + method.id().display(),
                branch.site()))
        .build();
  }
}
