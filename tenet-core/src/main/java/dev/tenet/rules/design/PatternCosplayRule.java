package dev.tenet.rules.design;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.TypeName;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.TreeSet;

public final class PatternCosplayRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-G05",
          "Pattern cosplay",
          Dimension.DESIGN,
          Severity.STRONG,
          1,
          "pattern names are earned by structure",
          "Name-vs-structure cross-check: Factory needs ≥2 constructible products, Builder needs "
              + "fluent accumulation plus a terminal build, Singleton needs a guarded single instance.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (cls.kind() != ClassFacts.Kind.CLASS || cls.isAbstract()) continue;
      claimBrokenBy(cls, analysis).ifPresent(broken -> findings.add(finding(cls, broken)));
    }
    return findings;
  }

  private Optional<String> claimBrokenBy(ClassFacts cls, Analysis analysis) {
    String simple = cls.name().simple();
    List<MethodFacts> methods = analysis.facts().methodsOf(cls);
    if (simple.endsWith("Factory")) return brokenFactoryClaim(methods, analysis);
    if (simple.endsWith("Builder")) return brokenBuilderClaim(methods);
    if (simple.endsWith("Singleton")) return brokenSingletonClaim(cls, analysis);
    return Optional.empty();
  }

  private Optional<String> brokenFactoryClaim(List<MethodFacts> methods, Analysis analysis) {
    TreeSet<TypeName> products = new TreeSet<>();
    for (MethodFacts method : methods) {
      boolean creates =
          method.returnsValue()
              && method.visibility().isAtLeastPackage()
              && analysis.facts().isRepoType(method.returnType());
      if (creates) products.add(method.returnType());
    }
    return products.size() <= 1
        ? Optional.of("claims Factory but constructs " + products.size() + " product type(s)")
        : Optional.empty();
  }

  private Optional<String> brokenBuilderClaim(List<MethodFacts> methods) {
    boolean accumulates = methods.stream().anyMatch(MethodFacts::returnsThis);
    boolean terminates = methods.stream().anyMatch(m -> m.name().equals("build"));
    if (accumulates && terminates) return Optional.empty();
    return Optional.of(
        "claims Builder but "
            + (accumulates ? "has no terminal build()" : "never accumulates fluently"));
  }

  private Optional<String> brokenSingletonClaim(ClassFacts cls, Analysis analysis) {
    for (var ctorId : cls.constructors()) {
      Optional<MethodFacts> ctor = analysis.facts().method(ctorId);
      if (ctor.isPresent() && ctor.get().visibility().isAtLeastPackage()) {
        return Optional.of("claims Singleton but exposes a non-private constructor");
      }
    }
    return Optional.empty();
  }

  private Finding finding(ClassFacts cls, String broken) {
    return Finding.builder(DESCRIPTOR.id(), cls.name().simple() + " " + broken)
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(cls.site())
        .witness("claim", "the class name asserts a GoF pattern")
        .witness("structure", broken)
        .suggestion("implement the pattern's obligations, or rename to what the class actually is")
        .certificate(new Certificate.Syntactic(broken, cls.site()))
        .build();
  }
}
