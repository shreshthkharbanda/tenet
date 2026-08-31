package dev.tenet.rules.types;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.FieldFacts;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public final class BooleanStateMachineRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-D02",
          "Boolean state machine",
          Dimension.TYPES,
          Severity.STRONG,
          2,
          "illegal states are unrepresentable",
          "Construction/assignment-site analysis: every writer rewrites the whole flag group "
              + "and never sets two true — the exclusion invariant is maintained, not assumed.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      List<FieldFacts> booleans = cls.booleanInstanceFields();
      if (booleans.size() < 2) continue;
      evaluateClass(cls, booleans, analysis, findings);
    }
    return findings;
  }

  private void evaluateClass(
      ClassFacts cls, List<FieldFacts> booleans, Analysis analysis, List<Finding> findings) {
    Set<String> fieldNames = new TreeSet<>();
    booleans.forEach(f -> fieldNames.add(f.id().name()));

    List<MethodId> writers = new ArrayList<>();
    Set<String> fieldsEverTrue = new TreeSet<>();
    for (MethodFacts method : analysis.facts().methodsOf(cls)) {
      Set<String> setTrue = new TreeSet<>(method.ownBooleanFieldsSetTrue());
      setTrue.retainAll(fieldNames);
      if (setTrue.isEmpty()) continue;
      if (setTrue.size() > 1) return;
      if (!method.ownFieldsAccessed().containsAll(fieldNames)) return;
      writers.add(method.id());
      fieldsEverTrue.addAll(setTrue);
    }
    if (fieldsEverTrue.size() < 2) return;
    findings.add(finding(cls, fieldNames, writers, fieldsEverTrue));
  }

  private Finding finding(
      ClassFacts cls, Set<String> fieldNames, List<MethodId> writers, Set<String> fieldsEverTrue) {
    int representable = 1 << fieldNames.size();
    int legal = fieldsEverTrue.size() + 1;
    return Finding.builder(
            DESCRIPTOR.id(),
            cls.name().simple() + " hides a state machine in " + fieldNames.size() + " booleans")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(cls.site())
        .witness("fields", String.join(", ", fieldNames))
        .witness(
            "statespace", representable + " representable states for ~" + legal + " legal ones")
        .witness("proof", writers.size() + " writer methods; none ever sets two fields true")
        .suggestion("replace the flags with one enum (or sealed hierarchy) naming the legal states")
        .certificate(new Certificate.MutualExclusion(cls.name(), fieldNames, writers))
        .build();
  }
}
