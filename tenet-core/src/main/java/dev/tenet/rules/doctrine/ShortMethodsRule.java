package dev.tenet.rules.doctrine;

import dev.tenet.analysis.Analysis;
import dev.tenet.engine.TenetConfig;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class ShortMethodsRule implements Rule {

  private static final String ID = "TNT-CC01";

  private final int maxStatements;
  private final RuleDescriptor descriptor;

  public ShortMethodsRule(TenetConfig config) {
    this.maxStatements = config.intParam(ID, "maxStatements", 25);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Method too long",
            Dimension.SHAPE,
            Severity.ADVISORY,
            1,
            "clean-code doctrine: a method does one thing and stays small",
            "Statement count above "
                + maxStatements
                + ". Contested territory: the deep-modules doctrine holds that cohesive length "
                + "beats extraction; enable one school, not both.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (method.statementCount() > maxStatements) {
        findings.add(finding(method));
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method) {
    return Finding.builder(ID, method.name() + "() has " + method.statementCount() + " statements")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(method.site())
        .witness("statements", method.statementCount() + " (doctrine limit " + maxStatements + ")")
        .suggestion("extract cohesive steps into named methods")
        .certificate(
            new Certificate.Syntactic(
                method.statementCount() + " statements in " + method.id().display(), method.site()))
        .build();
  }
}
