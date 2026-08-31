package dev.tenet.rules.names;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import dev.tenet.rules.support.Names;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class LyingQueryRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-A01",
          "Lying query",
          Dimension.NAMES,
          Severity.STRONG,
          1,
          "a name is a contract; the code must honor it",
          "Cross-checks the JavaBeans accessor verbs (get, is, has) against the effect graph; "
              + "flags only when the proven terminal effect changes state or writes to the world. "
              + "Queries that read the world are the point of many libraries and are not lies. "
              + "Queries sharing one terminal effect report once, as a shared root cause.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    Map<MethodId, List<MethodFacts>> byTerminal = new TreeMap<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (!looksLikeQuery(method)) continue;
      if (!analysis.purity().isProvenImpure(method.id())) continue;
      List<MethodId> chain = analysis.callGraph().effectChain(method.id());
      if (chain.isEmpty() || !terminalIsWriteShaped(chain, analysis)) continue;
      byTerminal.computeIfAbsent(chain.get(chain.size() - 1), key -> new ArrayList<>()).add(method);
    }
    List<Finding> findings = new ArrayList<>();
    for (List<MethodFacts> queries : byTerminal.values()) {
      MethodFacts anchor = queries.get(0);
      List<String> path = analysis.callGraph().effectPath(anchor.id()).orElse(List.of());
      findings.add(finding(anchor, queries, path, analysis));
    }
    return findings;
  }

  private static final java.util.Set<String> CORE_QUERY_VERBS =
      java.util.Set.of("get", "is", "has");

  private boolean looksLikeQuery(MethodFacts method) {
    return !method.isConstructor()
        && method.returnsValue()
        && !method.returnsThis()
        && method.visibility().isAtLeastPackage()
        && CORE_QUERY_VERBS.contains(
            Names.verbPrefix(method.name()).toLowerCase(java.util.Locale.ROOT));
  }

  private boolean terminalIsWriteShaped(List<MethodId> chain, Analysis analysis) {
    return analysis
        .facts()
        .method(chain.get(chain.size() - 1))
        .flatMap(MethodFacts::firstProvenEffect)
        .map(effect -> effect.writeShaped(Names::startsWithQueryVerb))
        .orElse(false);
  }

  private Finding finding(
      MethodFacts method, List<MethodFacts> queries, List<String> path, Analysis analysis) {
    Finding.Builder builder =
        Finding.builder(DESCRIPTOR.id(), "Query " + method.name() + "() has side effects")
            .dimension(DESCRIPTOR.dimension())
            .severity(DESCRIPTOR.severity())
            .at(method.site())
            .witness("namePromises", "pure query (verb: " + Names.verbPrefix(method.name()) + ")")
            .witness("effectPath", String.join(" -> ", path));
    if (queries.size() > 1) {
      List<String> examples = new ArrayList<>();
      for (int i = 0; i < Math.min(3, queries.size()); i++) {
        examples.add(queries.get(i).name() + "()");
      }
      builder.witness(
          "sharedRootCause",
          queries.size()
              + " queries reach this same effect, including "
              + String.join(", ", examples));
    }
    return builder
        .suggestion(
            "split the effect into a separate command, or rename with a verb that admits the effect")
        .certificate(effectPathCertificate(method.id(), analysis))
        .build();
  }

  private Certificate effectPathCertificate(MethodId start, Analysis analysis) {
    List<MethodId> chain = analysis.callGraph().effectChain(start);
    String terminal =
        chain.isEmpty()
            ? ""
            : analysis
                .facts()
                .method(chain.get(chain.size() - 1))
                .flatMap(MethodFacts::firstProvenEffect)
                .map(effect -> effect.describe())
                .orElse("");
    return new Certificate.EffectPath(chain, terminal);
  }
}
