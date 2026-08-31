package dev.tenet.rules.state;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.FieldFacts;
import dev.tenet.facts.FieldId;
import dev.tenet.facts.FieldWrite;
import dev.tenet.facts.MethodFacts;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class AmbientStaticStateRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-C01",
          "Ambient static state",
          Dimension.STATE,
          Severity.STRONG,
          1,
          "state is injected, not ambient",
          "Non-final statics (or final references to mutable collections) with writes reachable "
              + "from methods; the writing method is the witness.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    Map<FieldId, FieldFacts> mutableStatics = collectMutableStatics(analysis);
    List<Finding> findings = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (method.name().endsWith("ForTesting")) continue;
      for (FieldWrite write : method.staticWrites()) {
        FieldFacts field = mutableStatics.get(write.field());
        if (field != null) {
          findings.add(finding(field, method, write));
        }
      }
    }
    return findings;
  }

  private Map<FieldId, FieldFacts> collectMutableStatics(Analysis analysis) {
    Map<FieldId, FieldFacts> result = new LinkedHashMap<>();
    analysis
        .facts()
        .classes()
        .values()
        .forEach(
            cls ->
                cls.fields().stream()
                    .filter(FieldFacts::isStatic)
                    .filter(f -> !f.type().qualified().startsWith("java.util.concurrent"))
                    .filter(f -> !f.isFinal() || f.isMutableCollection())
                    .forEach(f -> result.put(f.id(), f)));
    return result;
  }

  private Finding finding(FieldFacts field, MethodFacts writer, FieldWrite write) {
    return Finding.builder(DESCRIPTOR.id(), "Static " + field.id() + " is mutated at runtime")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(write.site())
        .witness(
            "field",
            field.id()
                + " : "
                + field.type().simple()
                + (field.isFinal() ? " (final, mutable collection)" : " (non-final)"))
        .witness("writtenBy", writer.display())
        .suggestion(
            "inject the state as a collaborator, or wrap it in an explicit, synchronized store")
        .certificate(new Certificate.Syntactic("static write to " + field.id(), write.site()))
        .build();
  }
}
