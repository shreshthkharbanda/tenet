package dev.tenet.rules.fault;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.UnboundedWait;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class UnboundedWaitRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-H07",
          "Unbounded wait",
          Dimension.FAULT,
          Severity.STRONG,
          1,
          "every wait has a deadline",
          "Future.get() with no timeout and CompletableFuture.join(), recorded at extraction.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (UnboundedWait wait : method.unboundedWaits()) {
        findings.add(finding(method, wait));
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, UnboundedWait wait) {
    String call =
        switch (wait.kind()) {
          case FUTURE_GET -> "Future.get() with no timeout";
          case FUTURE_JOIN -> "CompletableFuture.join()";
        };
    return Finding.builder(DESCRIPTOR.id(), method.name() + "() waits without a deadline")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(wait.site())
        .witness("wait", call + " on " + wait.callDisplay())
        .witness("hazard", "the calling thread is hostage to the slowest dependency")
        .suggestion("use get(timeout, unit) or orTimeout(...) and decide what a timeout means here")
        .certificate(new Certificate.Syntactic(call + " in " + method.id().display(), wait.site()))
        .build();
  }
}
