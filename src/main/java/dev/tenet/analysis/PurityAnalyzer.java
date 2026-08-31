package dev.tenet.analysis;

import dev.tenet.facts.DirectEffect;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.facts.ProgramFacts;
import java.util.HashMap;
import java.util.Map;

public final class PurityAnalyzer {

  public PurityReport analyze(ProgramFacts facts) {
    Map<MethodId, Boolean> escapingSeeds = new HashMap<>();
    Map<MethodId, Boolean> selfSeeds = new HashMap<>();
    for (MethodFacts method : facts.methods().values()) {
      escapingSeeds.put(method.id(), method.firstEscapingEffect().isPresent());
      selfSeeds.put(method.id(), method.firstSelfStateWrite().isPresent());
    }
    Map<MethodId, Boolean> impure = propagate(facts, escapingSeeds, (from, to) -> true);
    Map<MethodId, Boolean> selfImpure =
        propagate(facts, selfSeeds, (from, to) -> from.owner().equals(to.owner()));
    Map<MethodId, Purity> verdicts = new HashMap<>();
    for (MethodFacts method : facts.methods().values()) {
      verdicts.put(method.id(), verdictOf(method, impure, selfImpure));
    }
    return new PurityReport(propagateUnknown(facts, verdicts));
  }

  private Purity verdictOf(
      MethodFacts method, Map<MethodId, Boolean> impure, Map<MethodId, Boolean> selfImpure) {
    if (impure.get(method.id()) || selfImpure.get(method.id())) return Purity.IMPURE_PROVEN;
    if (method.hasUnknownExternal() || hasLoggingEffect(method)) return Purity.UNKNOWN;
    return Purity.PURE;
  }

  private Map<MethodId, Boolean> propagate(
      ProgramFacts facts,
      Map<MethodId, Boolean> seeds,
      java.util.function.BiPredicate<MethodId, MethodId> edgeAllowed) {
    Map<MethodId, Boolean> reached = new HashMap<>(seeds);
    boolean changed = true;
    while (changed) {
      changed = false;
      for (MethodFacts method : facts.methods().values()) {
        if (reached.get(method.id())) continue;
        for (MethodId callee : method.callees()) {
          boolean caught =
              Boolean.TRUE.equals(reached.get(callee)) && edgeAllowed.test(method.id(), callee);
          if (caught) {
            reached.put(method.id(), true);
            changed = true;
            break;
          }
        }
      }
    }
    return reached;
  }

  private Map<MethodId, Purity> propagateUnknown(
      ProgramFacts facts, Map<MethodId, Purity> seeds) {
    Map<MethodId, Purity> verdicts = new HashMap<>(seeds);
    boolean changed = true;
    while (changed) {
      changed = false;
      for (MethodFacts method : facts.methods().values()) {
        if (verdicts.get(method.id()) != Purity.PURE) continue;
        for (MethodId callee : method.callees()) {
          if (verdicts.get(callee) == Purity.UNKNOWN) {
            verdicts.put(method.id(), Purity.UNKNOWN);
            changed = true;
            break;
          }
        }
      }
    }
    return verdicts;
  }

  private boolean hasLoggingEffect(MethodFacts method) {
    return method.effects().stream().anyMatch(e -> e.kind() == DirectEffect.Kind.LOG_CALL);
  }
}
