package dev.tenet.rules.names;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.FieldFacts;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.model.SourceRef;
import dev.tenet.rules.Rule;
import dev.tenet.rules.support.Names;
import java.util.ArrayList;
import java.util.List;

public final class BooleanPredicateRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-A02",
          "Boolean not a predicate",
          Dimension.NAMES,
          Severity.STRONG,
          1,
          "booleans read as claims",
          "Boolean-typed members whose names fail predicate grammar; record accessors "
              + "and overrides exempt (their names are fixed elsewhere).");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (cls.kind() == ClassFacts.Kind.RECORD) continue;
      collectFieldFindings(cls, findings);
      collectMethodFindings(cls, analysis, findings);
    }
    return findings;
  }

  private void collectFieldFindings(ClassFacts cls, List<Finding> findings) {
    for (FieldFacts field : cls.fields()) {
      boolean flaggable =
          field.isBoolean()
              && field.visibility().isAtLeastPackage()
              && !Names.readsAsPredicate(field.id().name());
      if (flaggable) {
        findings.add(finding("field " + field.id(), field.id().name(), field.site()));
      }
    }
  }

  private void collectMethodFindings(ClassFacts cls, Analysis analysis, List<Finding> findings) {
    for (MethodFacts method : analysis.facts().methodsOf(cls)) {
      boolean flaggable =
          method.returnsValue()
              && isBooleanType(method)
              && method.params().isEmpty()
              && method.visibility().isAtLeastPackage()
              && !method.isTrivialAccessor()
              && !method.isOverrideAnnotated()
              && !Names.readsAsPredicate(method.name());
      if (flaggable) {
        findings.add(
            finding("method " + method.id().display() + "()", method.name(), method.site()));
      }
    }
  }

  private boolean isBooleanType(MethodFacts method) {
    String qualified = method.returnType().qualified();
    return qualified.equals("boolean") || qualified.equals("java.lang.Boolean");
  }

  private Finding finding(String member, String name, SourceRef site) {
    return Finding.builder(DESCRIPTOR.id(), "Boolean " + name + " does not read as a predicate")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(site)
        .witness("member", member)
        .witness("grammar", "expected is/has/can/should/was/does... or an accepted predicate word")
        .suggestion("rename so the name asserts a claim, e.g. is" + capitalize(name))
        .certificate(new Certificate.Syntactic("boolean member named " + name, site))
        .build();
  }

  private String capitalize(String name) {
    return name.isEmpty() ? name : Character.toUpperCase(name.charAt(0)) + name.substring(1);
  }
}
