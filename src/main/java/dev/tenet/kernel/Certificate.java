package dev.tenet.kernel;

import dev.tenet.facts.MethodId;
import dev.tenet.facts.TypeName;
import dev.tenet.model.SourceRef;
import java.util.List;
import java.util.Set;

public sealed interface Certificate {

  record EffectPath(List<MethodId> chain, String terminalEffect) implements Certificate {
    public EffectPath {
      chain = List.copyOf(chain);
    }
  }

  record CallSiteSet(MethodId target, int paramIndex, List<SourceRef> sites, Set<String> literals)
      implements Certificate {
    public CallSiteSet {
      sites = List.copyOf(sites);
      literals = Set.copyOf(literals);
    }
  }

  record MutualExclusion(TypeName type, Set<String> booleanFields, List<MethodId> writers)
      implements Certificate {
    public MutualExclusion {
      booleanFields = Set.copyOf(booleanFields);
      writers = List.copyOf(writers);
    }
  }

  record Partition(TypeName type, List<Set<String>> components) implements Certificate {
    public Partition {
      components = List.copyOf(components);
    }
  }

  record Reachability(List<MethodId> chain) implements Certificate {
    public Reachability {
      chain = List.copyOf(chain);
    }
  }

  record HashCollision(String hash, List<MethodId> methods) implements Certificate {
    public HashCollision {
      methods = List.copyOf(methods);
    }
  }

  record Syntactic(String fact, SourceRef site) implements Certificate {}
}
