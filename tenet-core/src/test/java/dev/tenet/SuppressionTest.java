package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertTrue;

import dev.tenet.engine.EvidenceEngine;
import dev.tenet.engine.Report;
import dev.tenet.frontend.javac.JavacFrontend;
import dev.tenet.kernel.Kernel;
import dev.tenet.rules.Rules;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class SuppressionTest {

  @Test
  void annotationSuppressesOneRuleInsideItsScope() throws Exception {
    EvidenceEngine engine = new EvidenceEngine(new JavacFrontend(), Rules.all(), new Kernel());
    Report report = engine.check(List.of(Path.of("examples", "demo")), List.of());

    boolean suppressedFieldFlagged =
        report.findings().stream()
            .anyMatch(f -> f.ruleId().equals("TNT-C01") && f.title().contains("DataManager.temp"));
    boolean unsuppressedFieldStillFires =
        report.findings().stream()
            .anyMatch(f -> f.ruleId().equals("TNT-C01") && f.title().contains("DataManager.flag"));

    assertTrue(!suppressedFieldFlagged, "suppressed finding leaked through");
    assertTrue(unsuppressedFieldStillFires, "suppression scope was wider than the annotated method");
    assertTrue(report.stats().suppressedFindings() >= 1, "suppression count missing from stats");
  }
}
