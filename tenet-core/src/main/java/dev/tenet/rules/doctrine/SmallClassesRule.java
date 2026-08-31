package dev.tenet.rules.doctrine;

import dev.tenet.analysis.Analysis;
import dev.tenet.engine.TenetConfig;
import dev.tenet.facts.ClassFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class SmallClassesRule implements Rule {

  private static final String ID = "TNT-CC02";

  private final int maxMembers;
  private final RuleDescriptor descriptor;

  public SmallClassesRule(TenetConfig config) {
    this.maxMembers = config.intParam(ID, "maxMembers", 20);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Class too large",
            Dimension.DESIGN,
            Severity.ADVISORY,
            1,
            "clean-code doctrine: a class has one reason to change and stays small",
            "Fields plus methods above "
                + maxMembers
                + ". Contested territory: the deep-modules doctrine prefers fewer, deeper "
                + "classes; enable one school, not both.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      int members = cls.fields().size() + cls.methods().size();
      if (cls.kind() == ClassFacts.Kind.CLASS && members > maxMembers) {
        findings.add(finding(cls, members));
      }
    }
    return findings;
  }

  private Finding finding(ClassFacts cls, int members) {
    return Finding.builder(ID, cls.name().simple() + " has " + members + " members")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(cls.site())
        .witness("members", members + " fields and methods (doctrine limit " + maxMembers + ")")
        .suggestion("split along responsibility seams into collaborating classes")
        .certificate(
            new Certificate.Syntactic(members + " members in " + cls.name().simple(), cls.site()))
        .build();
  }
}
