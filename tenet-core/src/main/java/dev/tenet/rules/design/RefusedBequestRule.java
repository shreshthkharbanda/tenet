package dev.tenet.rules.design;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class RefusedBequestRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-G03",
          "Refused bequest",
          Dimension.DESIGN,
          Severity.STRONG,
          2,
          "subtypes honor the contract or the contract is wrong",
          "Overrides whose entire body is throw new UnsupportedOperationException — "
              + "implementation evidence that the supertype's contract is too fat.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (method.isOverrideAnnotated() && method.throwsUnsupportedOnly()) {
        findings.add(finding(method));
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method) {
    return Finding.builder(
            DESCRIPTOR.id(), method.id().display() + " refuses its inherited contract")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(method.site())
        .witness("body", "unconditionally throws UnsupportedOperationException")
        .witness("meaning", "the subtype is telling you it cannot honor the supertype")
        .suggestion(
            "narrow the supertype (interface segregation) or replace inheritance with delegation")
        .certificate(
            new Certificate.Syntactic("refusing override " + method.id().display(), method.site()))
        .build();
  }
}
