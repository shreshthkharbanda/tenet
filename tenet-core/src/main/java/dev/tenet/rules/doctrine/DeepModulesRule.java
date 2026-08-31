package dev.tenet.rules.doctrine;

import dev.tenet.analysis.Analysis;
import dev.tenet.engine.TenetConfig;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.Visibility;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class DeepModulesRule implements Rule {

  private static final String ID = "TNT-DM01";

  private final int minPublicMethods;
  private final RuleDescriptor descriptor;

  public DeepModulesRule(TenetConfig config) {
    this.minPublicMethods = config.intParam(ID, "minPublicMethods", 4);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Shallow module",
            Dimension.DESIGN,
            Severity.ADVISORY,
            1,
            "deep-modules doctrine: a small interface should hide substantial work",
            "A class whose public surface (methods) is larger than everything it hides "
                + "(private members plus implementation statements per public method). "
                + "Contested territory: the clean-code doctrine prefers many small units; "
                + "enable one school, not both.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (cls.kind() != ClassFacts.Kind.CLASS) continue;
      evaluateClass(cls, analysis, findings);
    }
    return findings;
  }

  private void evaluateClass(ClassFacts cls, Analysis analysis, List<Finding> findings) {
    int publicMethods = 0;
    int hiddenMembers = cls.instanceFields().size();
    int publicStatements = 0;
    for (MethodFacts method : analysis.facts().methodsOf(cls)) {
      if (method.isConstructor()) continue;
      if (method.visibility() == Visibility.PUBLIC) {
        publicMethods++;
        publicStatements += method.statementCount();
      } else {
        hiddenMembers++;
      }
    }
    boolean shallow =
        publicMethods >= minPublicMethods
            && hiddenMembers < publicMethods
            && publicStatements < publicMethods * 3;
    if (shallow) {
      findings.add(finding(cls, publicMethods, hiddenMembers, publicStatements));
    }
  }

  private Finding finding(ClassFacts cls, int publicMethods, int hidden, int statements) {
    return Finding.builder(ID, cls.name().simple() + " is a shallow module")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(cls.site())
        .witness(
            "surface",
            publicMethods + " public methods over " + hidden + " hidden members and "
                + statements + " implementation statements")
        .suggestion("merge thin wrappers into a deeper class, or give the surface real work to hide")
        .certificate(
            new Certificate.Syntactic(
                publicMethods + " public methods, " + hidden + " hidden in " + cls.name().simple(),
                cls.site()))
        .build();
  }
}
