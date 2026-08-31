package dev.tenet.rules.design;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.FieldFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import dev.tenet.rules.support.PackageProfiles;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class ConcreteReachDownRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-G04",
          "Concrete reach-down",
          Dimension.DESIGN,
          Severity.STRONG,
          2,
          "dependencies point toward abstractions",
          "A class in a pure-majority (domain-looking) package holding a field of an "
              + "infrastructure type — SDK client, JDBC, HTTP — instead of an owned interface.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    Map<String, PackageProfiles.Profile> profiles = PackageProfiles.of(analysis);
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      PackageProfiles.Profile profile = profiles.get(cls.name().packageName());
      if (profile == null || !profile.pureMajority()) continue;
      for (FieldFacts field : cls.fields()) {
        if (field.isInfraType()) {
          findings.add(finding(cls, field));
        }
      }
    }
    return findings;
  }

  private Finding finding(ClassFacts cls, FieldFacts field) {
    return Finding.builder(
            DESCRIPTOR.id(),
            cls.name().simple() + " welds domain logic to " + field.type().simple())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(field.site())
        .witness("field", field.id() + " : " + field.type().qualified())
        .witness(
            "context", "package " + cls.name().packageName() + " is pure-majority (domain-shaped)")
        .suggestion("define an interface this package owns; let an adapter hold the vendor type")
        .certificate(
            new Certificate.Syntactic(
                "infrastructure field " + field.id() + " in domain package", field.site()))
        .build();
  }
}
