package dev.tenet.rules.fault;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ExternalCall;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.facts.RetryScope;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class CompoundingRetriesRule implements Rule {

  private static final int AWS_SDK_DEFAULT_ATTEMPTS = 3;

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-H05",
          "Compounding retries",
          Dimension.FAULT,
          Severity.PROVEN,
          2,
          "retries live at exactly one layer",
          "Call-graph reachability between two recognized retry scopes; AWS SDK clients count as "
              + "an inner retry layer at their default policy. Witness carries the attempt product.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<MethodFacts> retriers = retriers(analysis);
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts outer : retriers) {
      collectStackedRepoRetries(outer, retriers, analysis, findings);
      collectSdkLayer(outer, findings);
    }
    return findings;
  }

  private List<MethodFacts> retriers(Analysis analysis) {
    List<MethodFacts> result = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (!method.retryScopes().isEmpty()) result.add(method);
    }
    return result;
  }

  private void collectStackedRepoRetries(
      MethodFacts outer, List<MethodFacts> retriers, Analysis analysis, List<Finding> findings) {
    for (MethodFacts inner : retriers) {
      if (inner.id().equals(outer.id())) continue;
      List<MethodId> chain = analysis.callGraph().chainBetween(outer.id(), inner.id());
      if (chain.size() >= 2) {
        findings.add(stackedFinding(outer, inner, chain));
      }
    }
  }

  private void collectSdkLayer(MethodFacts outer, List<Finding> findings) {
    for (RetryScope scope : outer.retryScopes()) {
      scope.externalCallsInTry().stream()
          .filter(this::isAwsSdk)
          .findFirst()
          .ifPresent(sdkCall -> findings.add(sdkFinding(outer, scope, sdkCall)));
    }
  }

  private boolean isAwsSdk(ExternalCall call) {
    String owner = call.owner().qualified();
    return owner.startsWith("software.amazon.awssdk") || owner.startsWith("com.amazonaws");
  }

  private Finding stackedFinding(MethodFacts outer, MethodFacts inner, List<MethodId> chain) {
    List<String> displays = new ArrayList<>();
    chain.forEach(id -> displays.add(id.display()));
    return Finding.builder(
            DESCRIPTOR.id(),
            outer.name() + "() retries around " + inner.name() + "(), which also retries")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(outer.retryScopes().get(0).site())
        .witness("outerRetry", outer.display())
        .witness("innerRetry", inner.display())
        .witness("callPath", String.join(" -> ", displays))
        .witness("attemptProduct", "attempts multiply across the layers (m x n)")
        .suggestion("retry at exactly one layer; remove the outer loop or the inner policy")
        .certificate(new Certificate.Reachability(chain))
        .build();
  }

  private Finding sdkFinding(MethodFacts outer, RetryScope scope, ExternalCall sdkCall) {
    return Finding.builder(
            DESCRIPTOR.id(),
            outer.name() + "() retries around an AWS SDK client that already retries")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(scope.site())
        .witness("outerRetry", "application loop at " + scope.site())
        .witness(
            "innerRetry",
            sdkCall.display() + " (SDK default policy: " + AWS_SDK_DEFAULT_ATTEMPTS + " attempts)")
        .witness("attemptProduct", "outer attempts x " + AWS_SDK_DEFAULT_ATTEMPTS)
        .suggestion(
            "disable client-level retries for this call path, or remove the application loop")
        .certificate(
            new Certificate.Syntactic(
                "retry scope wrapping SDK call " + sdkCall.display(), scope.site()))
        .build();
  }
}
