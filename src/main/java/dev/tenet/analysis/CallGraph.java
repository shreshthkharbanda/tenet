package dev.tenet.analysis;

import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.facts.ProgramFacts;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Predicate;

public final class CallGraph {

  private final ProgramFacts facts;
  private final Map<MethodId, List<MethodId>> effectChainMemo = new HashMap<>();

  public CallGraph(ProgramFacts facts) {
    this.facts = Objects.requireNonNull(facts, "facts");
  }

  public List<MethodId> effectChain(MethodId start) {
    return effectChainMemo.computeIfAbsent(start, this::computeEffectChain);
  }

  private List<MethodId> computeEffectChain(MethodId start) {
    List<MethodId> escaping =
        new Walk(facts, (from, to) -> true).from(start, this::hasEscapingEffect);
    if (!escaping.isEmpty()) return escaping;
    return new Walk(facts, (from, to) -> from.owner().equals(to.owner()))
        .from(start, this::hasSelfStateWrite);
  }

  public Optional<List<String>> effectPath(MethodId start) {
    List<MethodId> chain = effectChain(start);
    if (chain.isEmpty()) return Optional.empty();
    List<String> displays = new ArrayList<>();
    for (MethodId id : chain) {
      displays.add(facts.method(id).map(MethodFacts::display).orElseGet(id::toString));
    }
    facts
        .method(chain.get(chain.size() - 1))
        .flatMap(MethodFacts::firstProvenEffect)
        .ifPresent(effect -> displays.add(effect.describe()));
    return Optional.of(List.copyOf(displays));
  }

  public List<MethodId> chainBetween(MethodId from, MethodId to) {
    return new Walk(facts, (a, b) -> true).from(from, to::equals);
  }

  private boolean hasEscapingEffect(MethodId id) {
    return facts.method(id).flatMap(MethodFacts::firstEscapingEffect).isPresent();
  }

  private boolean hasSelfStateWrite(MethodId id) {
    return facts.method(id).flatMap(MethodFacts::firstSelfStateWrite).isPresent();
  }

  private static final class Walk {
    private final ProgramFacts facts;
    private final Map<MethodId, MethodId> parents = new HashMap<>();
    private final Deque<MethodId> frontier = new ArrayDeque<>();

    private final java.util.function.BiPredicate<MethodId, MethodId> edgeAllowed;

    private Walk(
        ProgramFacts facts, java.util.function.BiPredicate<MethodId, MethodId> edgeAllowed) {
      this.facts = facts;
      this.edgeAllowed = edgeAllowed;
    }

    private List<MethodId> from(MethodId start, Predicate<MethodId> goal) {
      parents.put(start, start);
      frontier.add(start);
      while (!frontier.isEmpty()) {
        MethodId current = frontier.poll();
        if (goal.test(current)) return chainTo(current);
        expand(current);
      }
      return List.of();
    }

    private void expand(MethodId current) {
      Optional<MethodFacts> m = facts.method(current);
      if (m.isEmpty()) return;
      for (MethodId callee : m.get().callees()) {
        boolean firstVisit =
            facts.methods().containsKey(callee)
                && edgeAllowed.test(current, callee)
                && parents.putIfAbsent(callee, current) == null;
        if (firstVisit) frontier.add(callee);
      }
    }

    private List<MethodId> chainTo(MethodId end) {
      Deque<MethodId> chain = new ArrayDeque<>();
      MethodId walk = end;
      while (true) {
        chain.addFirst(walk);
        MethodId parent = parents.get(walk);
        if (walk.equals(parent)) break;
        walk = parent;
      }
      return List.copyOf(chain);
    }
  }
}
