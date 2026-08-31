package dev.tenet.rules.fault;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ExternalCall;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class UnboundedFanOutRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-H03",
          "Unbounded fan-out",
          Dimension.FAULT,
          Severity.ADVISORY,
          3,
          "concurrency has a budget",
          "Executors.newCachedThreadPool creates threads without limit; parallel streams in "
              + "methods that perform I/O fan out on the common pool. Both flagged as advisory.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      for (ExternalCall call : method.externalCalls()) {
        if (isUnboundedPool(call)) {
          findings.add(finding(method, call, "an unbounded thread pool"));
        } else if (isParallelStreamWithIo(call, method, analysis)) {
          findings.add(finding(method, call, "a parallel stream in an effectful method"));
        }
      }
    }
    return findings;
  }

  private boolean isUnboundedPool(ExternalCall call) {
    return call.owner().qualified().equals("java.util.concurrent.Executors")
        && call.method().equals("newCachedThreadPool");
  }

  private boolean isParallelStreamWithIo(ExternalCall call, MethodFacts method, Analysis analysis) {
    return call.method().equals("parallelStream") && analysis.purity().isProvenImpure(method.id());
  }

  private Finding finding(MethodFacts method, ExternalCall call, String shape) {
    return Finding.builder(DESCRIPTOR.id(), method.name() + "() fans out via " + shape)
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(call.site())
        .witness("call", call.display())
        .witness("hazard", "no limiter between input size and concurrent work")
        .suggestion(
            "bound the pool (fixed size, semaphore, batching) and size it to the constrained resource")
        .certificate(new Certificate.Syntactic(shape + " in " + method.id().display(), call.site()))
        .build();
  }
}
