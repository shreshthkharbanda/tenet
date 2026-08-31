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

public final class VagueIdentifierRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-A03",
          "Vague identifier",
          Dimension.NAMES,
          Severity.ADVISORY,
          1,
          "names carry domain meaning",
          "Banned-lemma list with scope weighting: only non-private members and types are held "
              + "to it; short-lived locals are not judged.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  private enum Member {
    TYPE("type"),
    FIELD("field"),
    METHOD("method");

    private final String label;

    Member(String label) {
      this.label = label;
    }
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (Names.isVague(cls.name().simple())) {
        findings.add(finding(Member.TYPE, cls.name().simple(), cls.site()));
      }
      collectMemberFindings(cls, analysis, findings);
    }
    return findings;
  }

  private void collectMemberFindings(ClassFacts cls, Analysis analysis, List<Finding> findings) {
    for (FieldFacts field : cls.fields()) {
      if (field.visibility().isAtLeastPackage() && Names.isVague(field.id().name())) {
        findings.add(finding(Member.FIELD, field.id().name(), field.site()));
      }
    }
    for (MethodFacts method : analysis.facts().methodsOf(cls)) {
      boolean flaggable =
          method.visibility().isAtLeastPackage()
              && !method.isConstructor()
              && Names.isVague(method.name());
      if (flaggable) {
        findings.add(finding(Member.METHOD, method.name(), method.site()));
      }
    }
  }

  private Finding finding(Member member, String name, SourceRef site) {
    return Finding.builder(DESCRIPTOR.id(), "Vague " + member.label + " name: " + name)
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(site)
        .witness("name", name)
        .witness("why", "the name says nothing the type does not already say")
        .suggestion("rename with the domain concept the " + member.label + " actually represents")
        .certificate(new Certificate.Syntactic("vague " + member.label + " name " + name, site))
        .build();
  }
}
