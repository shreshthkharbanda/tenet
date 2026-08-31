package dev.tenet.rules.design;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.SwitchOverEnum;
import dev.tenet.facts.TypeName;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

public final class ScatteredDispatchRule implements Rule {

  private static final String ID = "TNT-G02";

  private final int minClasses;
  private final RuleDescriptor descriptor;

  public ScatteredDispatchRule(dev.tenet.engine.TenetConfig config) {
    this.minClasses = config.intParam(ID, "minClasses", 3);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Scattered dispatch",
            Dimension.DESIGN,
            Severity.PROVEN,
            2,
            "open for extension, closed for modification",
            "Repo-wide discriminant index: switches keyed on the same in-repo enum across "
                + minClasses
                + "+ classes; the blast radius of 'add one constant' is the witness.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    Map<TypeName, List<SwitchOverEnum>> grouped = groupByEnum(analysis);
    for (Map.Entry<TypeName, List<SwitchOverEnum>> entry : grouped.entrySet()) {
      if (!analysis.facts().isRepoType(entry.getKey())) continue;
      if (classCount(entry.getValue()) < minClasses) continue;
      findings.add(finding(entry.getKey(), entry.getValue()));
    }
    return findings;
  }

  private Map<TypeName, List<SwitchOverEnum>> groupByEnum(Analysis analysis) {
    Map<TypeName, List<SwitchOverEnum>> grouped = new java.util.TreeMap<>();
    for (SwitchOverEnum sw : analysis.facts().enumSwitches()) {
      grouped.computeIfAbsent(sw.enumType(), key -> new ArrayList<>()).add(sw);
    }
    return grouped;
  }

  private int classCount(List<SwitchOverEnum> switches) {
    TreeSet<TypeName> owners = new TreeSet<>();
    switches.forEach(sw -> owners.add(sw.ownerClass()));
    return owners.size();
  }

  private Finding finding(TypeName enumType, List<SwitchOverEnum> switches) {
    List<String> sites = new ArrayList<>();
    switches.forEach(sw -> sites.add(sw.ownerClass().simple() + " (" + sw.site() + ")"));
    return Finding.builder(
            descriptor.id(),
            enumType.simple() + " is dispatched in " + classCount(switches) + " classes")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(switches.get(0).site())
        .witness("dispatchSites", String.join("; ", sites))
        .witness(
            "blastRadius",
            "adding one constant to "
                + enumType.simple()
                + " touches "
                + switches.size()
                + " switch sites")
        .suggestion(
            "centralize the dispatch: polymorphism on the enum, a strategy map, or a sealed hierarchy")
        .certificate(
            new Certificate.Syntactic(
                enumType.simple() + " switched at " + switches.size() + " sites",
                switches.get(0).site()))
        .build();
  }
}
