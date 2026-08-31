package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import dev.tenet.engine.EvidenceEngine;
import dev.tenet.engine.Report;
import dev.tenet.frontend.javac.JavacFrontend;
import dev.tenet.kernel.Kernel;
import dev.tenet.model.Finding;
import dev.tenet.rules.Rules;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class DemoFindingsTest {

  private static Report report;

  @BeforeAll
  static void runEngineOnDemo() throws Exception {
    EvidenceEngine engine = new EvidenceEngine(new JavacFrontend(), Rules.all(), new Kernel());
    report = engine.check(List.of(Path.of("examples", "demo")), List.of());
  }

  @Test
  void findsEverySeededRule() {
    Set<String> expected =
        new TreeSet<>(
            Set.of(
                "TNT-A01", "TNT-B01", "TNT-B02", "TNT-B03", "TNT-B04",
                "TNT-C01", "TNT-C02", "TNT-D01", "TNT-D02", "TNT-D03", "TNT-D04", "TNT-D05",
                "TNT-E01", "TNT-E02", "TNT-F01", "TNT-F02", "TNT-G02", "TNT-G03", "TNT-G05", "TNT-G06",
                "TNT-H01", "TNT-H02", "TNT-H04", "TNT-H05", "TNT-H07"));
    Set<String> found = new TreeSet<>();
    report.findings().forEach(finding -> found.add(finding.ruleId()));

    Set<String> missing = new TreeSet<>(expected);
    missing.removeAll(found);
    assertTrue(missing.isEmpty(), "seeded violations not found: " + missing);
  }

  @Test
  void kernelRejectsNothingFromShippedRules() {
    assertEquals(
        0,
        report.stats().rejectedCandidates(),
        "a shipped rule proposed a certificate the kernel refused — searcher bug");
  }

  @Test
  void everyFindingCarriesWitnessAndSuggestion() {
    for (Finding finding : report.findings()) {
      assertTrue(!finding.witness().isEmpty(), finding.ruleId() + " lacks a witness");
      assertTrue(!finding.suggestion().isBlank(), finding.ruleId() + " lacks a suggestion");
    }
  }

  @Test
  void demoCompilesCleanly() {
    assertEquals(0, report.stats().compilationErrors(), "demo sources must compile");
  }
}
