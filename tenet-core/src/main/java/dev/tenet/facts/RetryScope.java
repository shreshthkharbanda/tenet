package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.List;
import java.util.Objects;

public record RetryScope(
    SourceRef site,
    boolean bounded,
    boolean classifiedErrors,
    boolean hasDelay,
    boolean delayGrows,
    List<MethodId> inRepoCallsInTry,
    List<ExternalCall> externalCallsInTry) {

  public RetryScope {
    Objects.requireNonNull(site, "site");
    inRepoCallsInTry = List.copyOf(inRepoCallsInTry);
    externalCallsInTry = List.copyOf(externalCallsInTry);
  }

  public List<String> missingPolicyFacts() {
    List<String> missing = new java.util.ArrayList<>();
    if (!classifiedErrors) missing.add("error classification (catches broad exception type)");
    if (!bounded) missing.add("attempt cap (loop not bounded by a constant)");
    if (!hasDelay) missing.add("backoff delay (no sleep between attempts)");
    else if (!delayGrows) missing.add("delay growth (constant backoff, no exponential/jitter)");
    return List.copyOf(missing);
  }
}
