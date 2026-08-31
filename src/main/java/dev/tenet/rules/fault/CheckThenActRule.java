package dev.tenet.rules.fault;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.CheckThenAct;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class CheckThenActRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-H02",
          "Check-then-act race",
          Dimension.FAULT,
          Severity.STRONG,
          2,
          "compound operations on shared state are atomic",
          "A guard reading shared map/collection state whose branch writes the same state, "
              + "with no synchronized covering both — the atomic replacement is named in the finding.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (method.isSynchronized()) continue;
      for (CheckThenAct race : method.checkThenActs()) {
        findings.add(finding(method, race));
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, CheckThenAct race) {
    return Finding.builder(
            DESCRIPTOR.id(), method.name() + "() check-then-acts on shared " + race.stateDisplay())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(race.site())
        .witness("check", race.checkCall())
        .witness("act", race.actCall())
        .witness("hazard", "between check and act, another thread can interleave")
        .suggestion(
            "use the atomic form (computeIfAbsent/putIfAbsent) or hold one lock across both")
        .certificate(
            new Certificate.Syntactic(
                "check-then-act on " + race.stateDisplay() + " in " + method.id().display(),
                race.site()))
        .build();
  }
}
