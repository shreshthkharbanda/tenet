package dev.tenet.rules.types;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.CallSite;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.model.SourceRef;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

public final class StringlyTypedRule implements Rule {

  private static final String ID = "TNT-D01";

  private final int minCallSites;
  private final int maxDistinctLiterals;
  private final RuleDescriptor descriptor;

  public StringlyTypedRule(dev.tenet.engine.TenetConfig config) {
    this.minCallSites = config.intParam(ID, "minCallSites", 3);
    this.maxDistinctLiterals = config.intParam(ID, "maxDistinctLiterals", 6);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "String that wants to be an enum",
            Dimension.TYPES,
            Severity.PROVEN,
            2,
            "the compiler enforces the domain",
            "Call-site index: every in-repo call passes a literal from a set of at most "
                + maxDistinctLiterals
                + " values across at least "
                + minCallSites
                + " sites.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (int i = 0; i < method.params().size(); i++) {
        if (!method.params().get(i).type().qualified().equals("java.lang.String")) continue;
        evaluateParam(method, i, analysis).ifPresent(findings::add);
      }
    }
    return findings;
  }

  private Optional<Finding> evaluateParam(MethodFacts method, int paramIndex, Analysis analysis) {
    List<CallSite> sites = analysis.facts().callSitesOf(method.id());
    if (sites.size() < minCallSites) return Optional.empty();
    Set<String> literals = new TreeSet<>();
    List<SourceRef> siteRefs = new ArrayList<>();
    for (CallSite site : sites) {
      if (paramIndex >= site.arguments().size()) return Optional.empty();
      Optional<String> literal = site.arguments().get(paramIndex).literal();
      if (literal.isEmpty()) return Optional.empty();
      literals.add(literal.get());
      siteRefs.add(site.site());
    }
    if (literals.size() < 2 || literals.size() > maxDistinctLiterals) return Optional.empty();
    return Optional.of(finding(method, paramIndex, literals, siteRefs));
  }

  private Finding finding(
      MethodFacts method, int paramIndex, Set<String> literals, List<SourceRef> sites) {
    String paramName = method.params().get(paramIndex).name();
    return Finding.builder(
            descriptor.id(),
            "String " + paramName + " of " + method.name() + "() wants to be an enum")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(method.site())
        .witness("observedValues", String.join(", ", literals))
        .witness("callSites", sites.size() + " sites, all passing literals from this set")
        .suggestion("introduce an enum with these constants; the compiler then enforces the domain")
        .certificate(new Certificate.CallSiteSet(method.id(), paramIndex, sites, literals))
        .build();
  }
}
