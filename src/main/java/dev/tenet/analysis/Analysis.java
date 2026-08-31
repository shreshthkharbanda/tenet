package dev.tenet.analysis;

import dev.tenet.facts.ProgramFacts;
import java.util.Objects;

public record Analysis(ProgramFacts facts, PurityReport purity, CallGraph callGraph) {

  public Analysis {
    Objects.requireNonNull(facts, "facts");
    Objects.requireNonNull(purity, "purity");
    Objects.requireNonNull(callGraph, "callGraph");
  }

  public static Analysis of(ProgramFacts facts) {
    return new Analysis(facts, new PurityAnalyzer().analyze(facts), new CallGraph(facts));
  }
}
