package dev.tenet.rules.design;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class RoommateTypesRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-G06",
          "Roommate types",
          Dimension.DESIGN,
          Severity.PROVEN,
          1,
          "one top-level type per file",
          "Top-level type declarations grouped by source file; a file declaring more than one "
              + "is flagged with all its tenants. Nested and member types are not judged.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    Map<String, List<ClassFacts>> topLevelByFile = new TreeMap<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (cls.isNested()) continue;
      topLevelByFile.computeIfAbsent(cls.site().file(), key -> new ArrayList<>()).add(cls);
    }
    List<Finding> findings = new ArrayList<>();
    for (List<ClassFacts> tenants : topLevelByFile.values()) {
      if (tenants.size() > 1) {
        findings.add(finding(tenants));
      }
    }
    return findings;
  }

  private Finding finding(List<ClassFacts> tenants) {
    List<String> names = new ArrayList<>();
    tenants.forEach(cls -> names.add(cls.name().simple() + " (line " + cls.site().line() + ")"));
    ClassFacts anchor = tenants.get(1);
    return Finding.builder(DESCRIPTOR.id(), tenants.size() + " top-level types share one file")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(anchor.site())
        .witness("tenants", String.join(", ", names))
        .suggestion("give each top-level type its own file named after it")
        .certificate(
            new Certificate.Syntactic(
                tenants.size() + " top-level types in " + anchor.site().file(), anchor.site()))
        .build();
  }
}
