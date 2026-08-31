package dev.tenet.rules.types;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

public final class BagOfNullablesRule implements Rule {

  private static final int MIN_FIELDS = 5;
  
  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-D03",
          "Bag of nullables",
          Dimension.TYPES,
          Severity.PROVEN,
          2,
          "one type, one shape",
          "Construction-site analysis: two constructors assign fully disjoint field sets, "
              + "proof of two construction shapes living in one type.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (cls.instanceFields().size() < MIN_FIELDS || cls.constructors().size() < 2) continue;
      disjointPair(cls, analysis).ifPresent(pair -> findings.add(finding(cls, pair)));
    }
    return findings;
  }

  private Optional<DisjointPair> disjointPair(ClassFacts cls, Analysis analysis) {
    List<MethodFacts> ctors = new ArrayList<>();
    for (var id : cls.constructors()) {
      analysis.facts().method(id).ifPresent(ctors::add);
    }
    for (int i = 0; i < ctors.size(); i++) {
      for (int j = i + 1; j < ctors.size(); j++) {
        Set<String> first = ctors.get(i).fieldsAssignedInConstructor();
        Set<String> second = ctors.get(j).fieldsAssignedInConstructor();
        if (first.isEmpty() || second.isEmpty()) continue;
        if (disjoint(first, second)) {
          return Optional.of(new DisjointPair(ctors.get(i), first, ctors.get(j), second));
        }
      }
    }
    return Optional.empty();
  }

  private boolean disjoint(Set<String> first, Set<String> second) {
    return first.stream().noneMatch(second::contains);
  }

  private record DisjointPair(
      MethodFacts firstCtor,
      Set<String> firstFields,
      MethodFacts secondCtor,
      Set<String> secondFields) {}

  private Finding finding(ClassFacts cls, DisjointPair pair) {
    return Finding.builder(
            DESCRIPTOR.id(), cls.name().simple() + " is several types forced into one")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(cls.site())
        .witness("clusterA", pair.firstCtor().site() + " assigns " + pair.firstFields())
        .witness("clusterB", pair.secondCtor().site() + " assigns " + pair.secondFields())
        .suggestion(
            "split along the clusters: a sealed hierarchy or two classes, one per construction shape")
        .certificate(
            new Certificate.Syntactic(
                "disjoint constructor field clusters in " + cls.name().simple(), cls.site()))
        .build();
  }
}
