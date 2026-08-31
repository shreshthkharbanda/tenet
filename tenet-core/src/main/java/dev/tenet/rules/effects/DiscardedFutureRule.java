package dev.tenet.rules.effects;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.DiscardedFuture;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class DiscardedFutureRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-E02",
          "Discarded future",
          Dimension.EFFECTS,
          Severity.STRONG,
          1,
          "every async failure has an owner",
          "An expression statement discarding a returned Future/CompletableFuture with no "
              + "failure handling attached anywhere on the chain.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (DiscardedFuture discarded : method.discardedFutures()) {
        if (!discarded.chainHandlesFailure()) {
          findings.add(finding(method, discarded));
        }
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, DiscardedFuture discarded) {
    return Finding.builder(
            DESCRIPTOR.id(), method.name() + "() drops the future from " + discarded.callDisplay())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(discarded.site())
        .witness("call", discarded.callDisplay())
        .witness("consequence", "its exception evaporates with it; ordering is unobservable")
        .suggestion(
            "await it, store it, or attach whenComplete/exceptionally so failure has an owner")
        .certificate(
            new Certificate.Syntactic(
                "discarded future from " + discarded.callDisplay() + " in " + method.id().display(),
                discarded.site()))
        .build();
  }
}
