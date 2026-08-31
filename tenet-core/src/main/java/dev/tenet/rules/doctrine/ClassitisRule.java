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
import java.util.Map;
import java.util.TreeMap;

public final class ClassitisRule implements Rule {

  private static final String ID = "TNT-DM02";

  private final int minClasses;
  private final int tinyMemberLimit;
  private final RuleDescriptor descriptor;

  public ClassitisRule(TenetConfig config) {
    this.minClasses = config.intParam(ID, "minClasses", 8);
    this.tinyMemberLimit = config.intParam(ID, "tinyMemberLimit", 4);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Classitis",
            Dimension.DESIGN,
            Severity.ADVISORY,
            1,
            "deep-modules doctrine: interfaces have a cost; do not multiply tiny units",
            "A package of "
                + minClasses
                + "+ top-level classes where most have at most "
                + tinyMemberLimit
                + " members each. Contested territory: the clean-code doctrine calls this "
                + "single responsibility; enable one school, not both.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    Map<String, List<ClassFacts>> byPackage = new TreeMap<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (cls.isNested() || cls.kind() != ClassFacts.Kind.CLASS) continue;
      byPackage.computeIfAbsent(cls.name().packageName(), key -> new ArrayList<>()).add(cls);
    }
    List<Finding> findings = new ArrayList<>();
    for (Map.Entry<String, List<ClassFacts>> entry : byPackage.entrySet()) {
      evaluatePackage(entry.getKey(), entry.getValue(), findings);
    }
    return findings;
  }

  private void evaluatePackage(String packageName, List<ClassFacts> classes, List<Finding> findings) {
    if (classes.size() < minClasses) return;
    long tiny =
        classes.stream()
            .filter(cls -> cls.fields().size() + cls.methods().size() <= tinyMemberLimit)
            .count();
    if (tiny * 2 > classes.size()) {
      findings.add(finding(packageName, classes, tiny));
    }
  }

  private Finding finding(String packageName, List<ClassFacts> classes, long tiny) {
    ClassFacts anchor = classes.get(0);
    return Finding.builder(ID, "Package " + packageName + " has classitis")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(anchor.site())
        .witness(
            "shape",
            tiny + " of " + classes.size() + " top-level classes have at most "
                + tinyMemberLimit + " members")
        .suggestion("merge fragmentary classes into fewer, deeper modules")
        .certificate(
            new Certificate.Syntactic(
                tiny + " tiny classes of " + classes.size() + " in " + packageName, anchor.site()))
        .build();
  }
}
