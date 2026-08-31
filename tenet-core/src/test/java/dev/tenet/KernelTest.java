package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertFalse;

import dev.tenet.facts.MethodId;
import dev.tenet.facts.ProgramFacts;
import dev.tenet.facts.TypeName;
import dev.tenet.kernel.Certificate;
import dev.tenet.kernel.Kernel;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class KernelTest {

  private final Kernel kernel = new Kernel();
  private final ProgramFacts empty = ProgramFacts.builder().build();

  @Test
  void rejectsEffectPathOverMissingMethods() {
    MethodId ghost = new MethodId(new TypeName("com.acme.Ghost"), "haunt", "()");
    Certificate lie = new Certificate.EffectPath(List.of(ghost), "calls Files.write [IO]");
    assertFalse(kernel.verify(lie, empty));
  }

  @Test
  void rejectsReachabilityWithoutEdges() {
    MethodId a = new MethodId(new TypeName("com.acme.A"), "outer", "()");
    MethodId b = new MethodId(new TypeName("com.acme.B"), "inner", "()");
    assertFalse(kernel.verify(new Certificate.Reachability(List.of(a, b)), empty));
  }

  @Test
  void rejectsHashCollisionOverMissingMethods() {
    MethodId ghost = new MethodId(new TypeName("com.acme.Ghost"), "copy", "()");
    MethodId ghost2 = new MethodId(new TypeName("com.acme.Ghost2"), "copy", "()");
    Certificate lie = new Certificate.HashCollision("deadbeef", List.of(ghost, ghost2));
    assertFalse(kernel.verify(lie, empty));
  }

  @Test
  void rejectsCallSiteSetWithNoObservedSites() {
    MethodId target = new MethodId(new TypeName("com.acme.A"), "transition", "(java.lang.String)");
    Certificate lie = new Certificate.CallSiteSet(target, 0, List.of(), Set.of("PENDING"));
    assertFalse(kernel.verify(lie, empty));
  }

  @Test
  void rejectsMutualExclusionWithoutWriters() {
    Certificate lie =
        new Certificate.MutualExclusion(
            new TypeName("com.acme.A"), Set.of("isLoading", "isFailed"), List.of());
    assertFalse(kernel.verify(lie, empty));
  }
}
