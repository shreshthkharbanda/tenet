package dev.tenet.kernel;

import dev.tenet.facts.CallSite;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.facts.ProgramFacts;
import dev.tenet.model.SourceRef;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

public final class Kernel {

  public boolean verify(Certificate certificate, ProgramFacts facts) {
    return switch (certificate) {
      case Certificate.EffectPath c -> verifyEffectPath(c, facts);
      case Certificate.CallSiteSet c -> verifyCallSiteSet(c, facts);
      case Certificate.MutualExclusion c -> verifyMutualExclusion(c, facts);
      case Certificate.Partition c -> verifyPartition(c, facts);
      case Certificate.Reachability c -> verifyReachability(c, facts);
      case Certificate.HashCollision c -> verifyHashCollision(c, facts);
      case Certificate.Syntactic c -> verifySyntactic(c);
    };
  }

  private boolean verifyEffectPath(Certificate.EffectPath cert, ProgramFacts facts) {
    List<MethodId> chain = cert.chain();
    if (chain.isEmpty() || !edgesExist(chain, facts)) return false;
    Optional<MethodFacts> last = facts.method(chain.get(chain.size() - 1));
    return last.isPresent()
        && last.get()
            .firstProvenEffect()
            .map(e -> e.describe().equals(cert.terminalEffect()))
            .orElse(false);
  }

  private boolean verifyCallSiteSet(Certificate.CallSiteSet cert, ProgramFacts facts) {
    List<CallSite> observed = facts.callSitesOf(cert.target());
    if (observed.size() != cert.sites().size() || observed.isEmpty()) return false;
    for (CallSite site : observed) {
      if (cert.paramIndex() >= site.arguments().size()) return false;
      Optional<String> literal = site.arguments().get(cert.paramIndex()).literal();
      if (literal.isEmpty() || !cert.literals().contains(literal.get())) return false;
    }
    return true;
  }

  private boolean verifyMutualExclusion(Certificate.MutualExclusion cert, ProgramFacts facts) {
    if (cert.writers().isEmpty()) return false;
    for (MethodId writer : cert.writers()) {
      Optional<MethodFacts> m = facts.method(writer);
      if (m.isEmpty()) return false;
      Set<String> setTrue = new HashSet<>(m.get().ownBooleanFieldsSetTrue());
      setTrue.retainAll(cert.booleanFields());
      if (setTrue.size() > 1) return false;
    }
    return true;
  }

  private boolean verifyPartition(Certificate.Partition cert, ProgramFacts facts) {
    Optional<ClassFacts> cls = facts.classOf(cert.type());
    if (cls.isEmpty() || cert.components().size() < 2) return false;
    for (MethodFacts m : facts.methodsOf(cls.get())) {
      Optional<Set<String>> home = componentOf(m.name(), cert.components());
      if (home.isEmpty()) continue;
      if (m.isStatic() || m.isConstructor()) continue;
      if (!home.get().containsAll(reachableMembers(m, cls.get(), facts))) return false;
    }
    return true;
  }

  private Optional<Set<String>> componentOf(String member, List<Set<String>> components) {
    return components.stream().filter(c -> c.contains(member)).findFirst();
  }

  private Set<String> reachableMembers(MethodFacts m, ClassFacts cls, ProgramFacts facts) {
    Set<String> reached = new HashSet<>(m.ownFieldsAccessed());
    for (MethodId callee : m.callees()) {
      boolean node =
          callee.owner().equals(cls.name())
              && facts.method(callee).map(c -> !c.isStatic() && !c.isConstructor()).orElse(false);
      if (node) reached.add(callee.name());
    }
    return reached;
  }

  private boolean verifyReachability(Certificate.Reachability cert, ProgramFacts facts) {
    return cert.chain().size() >= 2 && edgesExist(cert.chain(), facts);
  }

  private boolean verifyHashCollision(Certificate.HashCollision cert, ProgramFacts facts) {
    if (cert.methods().size() < 2) return false;
    for (MethodId id : cert.methods()) {
      Optional<MethodFacts> m = facts.method(id);
      if (m.isEmpty() || !m.get().bodyHash().map(cert.hash()::equals).orElse(false)) return false;
    }
    return true;
  }

  private boolean verifySyntactic(Certificate.Syntactic cert) {
    return !cert.fact().isBlank() && !SourceRef.UNKNOWN.equals(cert.site());
  }

  private boolean edgesExist(List<MethodId> chain, ProgramFacts facts) {
    for (int i = 0; i + 1 < chain.size(); i++) {
      Optional<MethodFacts> caller = facts.method(chain.get(i));
      if (caller.isEmpty() || !caller.get().callees().contains(chain.get(i + 1))) return false;
    }
    return true;
  }
}
