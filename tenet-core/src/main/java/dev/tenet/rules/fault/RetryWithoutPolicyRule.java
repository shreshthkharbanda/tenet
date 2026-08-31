package dev.tenet.rules.fault;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.RetryScope;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class RetryWithoutPolicyRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-H04",
          "Retry without a policy",
          Dimension.FAULT,
          Severity.STRONG,
          1,
          "a retry is a designed policy, not a loop",
          "Recognized retry scopes checked for three independent structural facts: error "
              + "classification, an attempt cap, and growing backoff. The witness names what's missing.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (RetryScope scope : method.retryScopes()) {
        List<String> missing = scope.missingPolicyFacts();
        if (!missing.isEmpty()) {
          findings.add(finding(method, scope, missing));
        }
      }
    }
    return findings;
  }

  private Finding finding(MethodFacts method, RetryScope scope, List<String> missing) {
    return Finding.builder(DESCRIPTOR.id(), method.name() + "() retries without a complete policy")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(scope.site())
        .witness("missing", String.join("; ", missing))
        .witness("retries", describeAttempts(scope))
        .suggestion(
            "classify retryable errors, cap attempts, and back off exponentially with jitter")
        .certificate(
            new Certificate.Syntactic(
                "retry scope missing "
                    + missing.size()
                    + " policy fact(s) in "
                    + method.id().display(),
                scope.site()))
        .build();
  }

  private String describeAttempts(RetryScope scope) {
    int calls = scope.inRepoCallsInTry().size() + scope.externalCallsInTry().size();
    return calls + " call(s) re-attempted at " + scope.site();
  }
}
