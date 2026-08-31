package dev.tenet.rules.types;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.SwitchOverEnum;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

public final class SilentNonExhaustiveRule implements Rule {

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-D04",
          "Silent non-exhaustiveness",
          Dimension.TYPES,
          Severity.PROVEN,
          1,
          "additions are loud",
          "A switch over an in-repo enum covering a strict subset of constants, with a default "
              + "(or fallthrough) that swallows the remainder instead of failing.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (SwitchOverEnum sw : analysis.facts().enumSwitches()) {
      analysis
          .facts()
          .classOf(sw.enumType())
          .ifPresent(
              enumClass -> {
                if (silentlyNonExhaustive(sw, enumClass)) {
                  findings.add(finding(sw, enumClass));
                }
              });
    }
    return findings;
  }

  private boolean silentlyNonExhaustive(SwitchOverEnum sw, ClassFacts enumClass) {
    boolean coversAll = sw.coveredConstants().containsAll(enumClass.enumConstants());
    boolean failsLoud = sw.hasDefault() && sw.defaultThrows();
    return !coversAll && !failsLoud;
  }

  private Finding finding(SwitchOverEnum sw, ClassFacts enumClass) {
    TreeSet<String> missing = new TreeSet<>(enumClass.enumConstants());
    sw.coveredConstants().forEach(missing::remove);
    return Finding.builder(
            DESCRIPTOR.id(),
            "Switch over "
                + sw.enumType().simple()
                + " silently skips "
                + missing.size()
                + " constants")
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(sw.site())
        .witness("missingConstants", String.join(", ", missing))
        .witness(
            "disposal", sw.hasDefault() ? "default swallows them" : "no default; they fall through")
        .suggestion(
            "cover every constant, or make the default throw so a new constant fails loudly")
        .certificate(
            new Certificate.Syntactic(
                "non-exhaustive switch over " + sw.enumType().simple(), sw.site()))
        .build();
  }
}
