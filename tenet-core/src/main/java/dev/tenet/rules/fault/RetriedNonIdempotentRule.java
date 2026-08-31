package dev.tenet.rules.fault;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ExternalCall;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.RetryScope;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import dev.tenet.rules.support.Names;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class RetriedNonIdempotentRule implements Rule {

  private static final Set<String> NON_IDEMPOTENT_PREFIXES =
      Set.of(
          "send", "put", "post", "insert", "create", "append", "add", "publish", "write", "enqueue",
          "emit");

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-H06",
          "Retried effect without idempotency",
          Dimension.FAULT,
          Severity.ADVISORY,
          3,
          "retried work is safe to repeat",
          "Effect-shape classification of calls inside recognized retry scopes; proves the hazard "
              + "pattern, not semantic idempotency — advisory by design.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (RetryScope scope : method.retryScopes()) {
        for (ExternalCall call : scope.externalCallsInTry()) {
          if (looksNonIdempotent(call)) {
            findings.add(finding(method, scope, call));
          }
        }
      }
    }
    return findings;
  }

  private boolean looksNonIdempotent(ExternalCall call) {
    if (call.effectClass() != ExternalCall.EffectClass.IO) return false;
    String verb = Names.verbPrefix(call.method()).toLowerCase(Locale.ROOT);
    return NON_IDEMPOTENT_PREFIXES.contains(verb);
  }

  private Finding finding(MethodFacts method, RetryScope scope, ExternalCall call) {
    return Finding.builder(
            DESCRIPTOR.id(), method.name() + "() retries non-idempotent-shaped " + call.display())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(call.site())
        .witness("retryScope", scope.site().toString())
        .witness("call", call.display() + " (create/send/append shape)")
        .suggestion(
            "attach an idempotency key or dedupe token, or make the operation a keyed upsert")
        .certificate(
            new Certificate.Syntactic(
                "non-idempotent-shaped call " + call.display() + " inside retry scope",
                call.site()))
        .build();
  }
}
