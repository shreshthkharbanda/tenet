package dev.tenet.rules.truth;

import dev.tenet.analysis.Analysis;
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
import java.util.Map;
import java.util.TreeSet;

public final class DuplicateLogicRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-F01",
          "Duplicate logic",
          Dimension.TRUTH,
          Severity.PROVEN,
          2,
          "one fact, one place",
          "Normalized-AST hashing: trivia stripped, locals alpha-renamed, bodies hashed; "
              + "exact-after-normalization collisions across classes only.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (Map.Entry<String, List<MethodId>> group : analysis.facts().bodyHashGroups().entrySet()) {
      if (group.getValue().size() < 2 || !spansMultipleOwners(group.getValue())) continue;
      finding(group.getKey(), group.getValue(), analysis).ifPresent(findings::add);
    }
    return findings;
  }

  private boolean spansMultipleOwners(List<MethodId> methods) {
    TreeSet<String> owners = new TreeSet<>();
    methods.forEach(id -> owners.add(id.owner().qualified()));
    return owners.size() >= 2;
  }

  private java.util.Optional<Finding> finding(
      String hash, List<MethodId> group, Analysis analysis) {
    List<String> sites = new ArrayList<>();
    MethodFacts anchor = null;
    for (MethodId id : group) {
      MethodFacts m = analysis.facts().method(id).orElse(null);
      if (m == null) return java.util.Optional.empty();
      if (anchor == null) anchor = m;
      sites.add(m.display());
    }
    return java.util.Optional.of(
        Finding.builder(DESCRIPTOR.id(), "Identical logic implemented " + group.size() + " times")
            .dimension(DESCRIPTOR.dimension())
            .severity(DESCRIPTOR.severity())
            .at(anchor.site())
            .witness("sites", String.join("; ", sites))
            .witness("proof", "normalized bodies hash identically and compare equal structurally")
            .suggestion(
                "extract one owner for this logic; the copies will diverge the day one is fixed")
            .certificate(new Certificate.HashCollision(hash, group))
            .build());
  }
}
