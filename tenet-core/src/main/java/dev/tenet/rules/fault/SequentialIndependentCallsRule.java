package dev.tenet.rules.fault;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.patterns.IndependentBlockingPair;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class SequentialIndependentCallsRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-H01",
          "Sequential independent calls",
          Dimension.FAULT,
          Severity.STRONG,
          1,
          "independent work runs concurrently",
          "Def-use analysis proves the second blocking call reads nothing the first defines "
              + "and no shared state is written between them — independence is a fact, not a guess.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (IndependentBlockingPair pair : method.independentBlockingPairs()) {
        if (readShaped(pair.firstCall()) && readShaped(pair.secondCall())) {
          findings.add(finding(method, pair));
        }
      }
    }
    return findings;
  }

  private boolean readShaped(String callText) {
    int lastDot = callText.lastIndexOf('.');
    String name = lastDot < 0 ? callText : callText.substring(lastDot + 1);
    return dev.tenet.rules.support.Names.startsWithQueryVerb(name);
  }

  private Finding finding(MethodFacts method, IndependentBlockingPair pair) {
    return Finding.builder(
            DESCRIPTOR.id(), method.name() + "() runs independent blocking calls sequentially")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(pair.firstSite())
        .witness("first", pair.firstCall() + " at " + pair.firstSite())
        .witness("second", pair.secondCall() + " at " + pair.secondSite())
        .witness(
            "independence", "second reads nothing the first defines; no interleaved shared write")
        .suggestion(
            "run them concurrently (CompletableFuture.allOf, structured concurrency) and join once")
        .certificate(
            new Certificate.Syntactic(
                "independent sequential blocking pair in " + method.id().display(),
                pair.firstSite()))
        .build();
  }
}
