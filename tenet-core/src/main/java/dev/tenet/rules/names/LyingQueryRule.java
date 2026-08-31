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

public final class LyingQueryRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-A01",
          "Lying query",
          Dimension.NAMES,
          Severity.STRONG,
          1,
          "a name is a contract; the code must honor it",
          "Cross-checks verb classification of the name against the transitive effect graph; "
              + "flags only when a concrete effect path is proven.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (!looksLikeQuery(method)) continue;
      if (!analysis.purity().isProvenImpure(method.id())) continue;
      analysis
          .callGraph()
          .effectPath(method.id())
          .ifPresent(path -> findings.add(finding(method, path, analysis)));
    }
    return findings;
  }

  private boolean looksLikeQuery(MethodFacts method) {
    return !method.isConstructor()
        && method.returnsValue()
        && !method.returnsThis()
        && method.visibility().isAtLeastPackage()
        && Names.startsWithQueryVerb(method.name());
  }

  private Finding finding(MethodFacts method, List<String> path, Analysis analysis) {
    return Finding.builder(DESCRIPTOR.id(), "Query " + method.name() + "() has side effects")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(method.site())
        .witness("namePromises", "pure query (verb: " + Names.verbPrefix(method.name()) + ")")
        .witness("effectPath", String.join(" -> ", path))
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
