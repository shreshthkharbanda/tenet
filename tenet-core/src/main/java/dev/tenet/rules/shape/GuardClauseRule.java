package dev.tenet.rules.shape;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.model.SourceRef;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class GuardClauseRule implements Rule {

  private static final String ID = "TNT-B03";

  private final int maxNesting;
  private final RuleDescriptor descriptor;

  public GuardClauseRule(dev.tenet.engine.TenetConfig config) {
    this.maxNesting = config.intParam(ID, "maxNesting", 3);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Guard-clause inversion",
            Dimension.SHAPE,
            Severity.PROVEN,
            1,
            "edge cases exit early; the happy path reads straight down",
            "Nesting depth beyond "
                + maxNesting
                + " where an enclosing branch is terminating and "
                + "therefore invertible into a guard — the invertible branch is the witness.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (method.maxNestingDepth() <= maxNesting) continue;
      method.invertibleGuard().ifPresent(guard -> findings.add(finding(method, guard)));
    }
    return findings;
  }

  private Finding finding(MethodFacts method, SourceRef guard) {
    return Finding.builder(
            descriptor.id(),
            method.name()
                + "() nests "
                + method.maxNestingDepth()
                + " deep with an invertible branch")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(guard)
        .witness("maxNesting", String.valueOf(method.maxNestingDepth()))
        .witness("invertibleBranch", guard.toString())
        .suggestion("invert the terminating branch into an early return and flatten the happy path")
        .certificate(
            new Certificate.Syntactic(
                "nesting "
                    + method.maxNestingDepth()
                    + " with invertible branch in "
                    + method.id().display(),
                guard))
        .build();
  }
}
