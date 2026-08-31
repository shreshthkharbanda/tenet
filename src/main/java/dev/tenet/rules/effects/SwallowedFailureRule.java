package dev.tenet.rules.effects;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.CatchFact;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class SwallowedFailureRule implements Rule {

  private static final List<String> BOUNDARY_SUFFIXES =
      List.of("Handler", "Controller", "Main", "Application", "Worker", "Runner", "Cli", "Command");

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-E01",
          "Swallowed failure",
          Dimension.EFFECTS,
          Severity.STRONG,
          1,
          "failure is handled at boundaries and designed, not muffled",
          "A catch that neither rethrows nor handles, outside boundary classes; swallowing "
              + "InterruptedException without re-interrupting is called out specially.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (CatchFact caught : method.catches()) {
        if (interruptMishandled(caught)) {
          findings.add(interruptFinding(method, caught));
        } else if (caught.swallows() && !isBoundary(method)) {
          findings.add(swallowFinding(method, caught));
        }
      }
    }
    return findings;
  }

  private boolean interruptMishandled(CatchFact caught) {
    return caught.catchesInterrupted()
        && !caught.reinterrupts()
        && caught.disposal() != CatchFact.Disposal.RETHROWS;
  }

  private boolean isBoundary(MethodFacts method) {
    if (method.name().equals("main")) return true;
    String owner = method.id().owner().simple();
    return BOUNDARY_SUFFIXES.stream().anyMatch(owner::endsWith);
  }

  private Finding swallowFinding(MethodFacts method, CatchFact caught) {
    return Finding.builder(DESCRIPTOR.id(), method.name() + "() swallows " + caught.caughtType())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(caught.site())
        .witness("caught", caught.caughtType())
        .witness(
            "disposal",
            caught.disposal().name().toLowerCase(java.util.Locale.ROOT).replace('_', ' '))
        .suggestion(
            "rethrow in your own vocabulary, return a typed failure, or handle at the boundary")
        .certificate(
            new Certificate.Syntactic(
                "swallowing catch of " + caught.caughtType() + " in " + method.id().display(),
                caught.site()))
        .build();
  }

  private Finding interruptFinding(MethodFacts method, CatchFact caught) {
    return Finding.builder(
            DESCRIPTOR.id(),
            method.name() + "() swallows InterruptedException without re-interrupting")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(caught.site())
        .witness("caught", caught.caughtType())
        .witness("missing", "Thread.currentThread().interrupt() before continuing")
        .suggestion("restore the interrupt flag, or rethrow; the thread's owner needs the signal")
        .certificate(
            new Certificate.Syntactic(
                "InterruptedException swallowed in " + method.id().display(), caught.site()))
        .build();
  }
}
