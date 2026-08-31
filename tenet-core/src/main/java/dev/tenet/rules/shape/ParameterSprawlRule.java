package dev.tenet.rules.shape;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.Param;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;

public final class ParameterSprawlRule implements Rule {

  private static final String ID = "TNT-B04";

  private final int maxParams;
  private final int adjacentSameType;
  private final RuleDescriptor descriptor;

  public ParameterSprawlRule(dev.tenet.engine.TenetConfig config) {
    this.maxParams = config.intParam(ID, "maxParams", 4);
    this.adjacentSameType = config.intParam(ID, "adjacentSameType", 3);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Parameter sprawl",
            Dimension.SHAPE,
            Severity.PROVEN,
            1,
            "a signature is an API; keep it graspable",
            "More than "
                + maxParams
                + " parameters, or "
                + adjacentSameType
                + "+ adjacent parameters of the same type (swappable at every call site). "
                + "Record constructors exempt: a record already is the parameter object.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (!method.visibility().isAtLeastPackage()) continue;
      if (method.isConstructor() && isRecordOwner(method, analysis)) continue;
      if (method.params().size() > maxParams) {
        findings.add(finding(method, "declares " + method.params().size() + " parameters"));
      } else {
        adjacentRun(method.params())
            .ifPresent(
                type ->
                    findings.add(
                        finding(
                            method, adjacentSameType + " adjacent parameters of type " + type)));
      }
    }
    return findings;
  }

  private boolean isRecordOwner(MethodFacts method, Analysis analysis) {
    return analysis
        .facts()
        .classOf(method.id().owner())
        .map(cls -> cls.kind() == dev.tenet.facts.ClassFacts.Kind.RECORD)
        .orElse(false);
  }

  private java.util.Optional<String> adjacentRun(List<Param> params) {
    int run = 1;
    for (int i = 1; i < params.size(); i++) {
      run = params.get(i).type().equals(params.get(i - 1).type()) ? run + 1 : 1;
      if (run >= adjacentSameType) {
        return java.util.Optional.of(params.get(i).type().simple());
      }
    }
    return java.util.Optional.empty();
  }

  private Finding finding(MethodFacts method, String evidence) {
    return Finding.builder(descriptor.id(), method.name() + "() " + evidence)
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(method.site())
        .witness("signature", method.name() + "/" + method.params().size())
        .witness("evidence", evidence)
        .suggestion(
            "introduce a parameter object or a builder; group the values that travel together")
        .certificate(
            new Certificate.Syntactic(evidence + " in " + method.id().display(), method.site()))
        .build();
  }
}
