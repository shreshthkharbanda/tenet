package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import dev.tenet.engine.Baseline;
import dev.tenet.engine.Report;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.Severity;
import dev.tenet.model.SourceRef;
import java.util.List;
import org.junit.jupiter.api.Test;

class BaselineTest {

  private Finding finding(String ruleId, String title) {
    return Finding.builder(ruleId, title)
        .dimension(Dimension.NAMES)
        .severity(Severity.STRONG)
        .at("src/A.java", 10)
        .witness("w", "v")
        .suggestion("s")
        .certificate(new Certificate.Syntactic("f", new SourceRef("src/A.java", 10)))
        .build();
  }

  private Report reportOf(List<Finding> findings) {
    return new Report(findings, new Report.Stats(1, 1, 1, 0, 0, 0, 0, 5));
  }

  @Test
  void baselinedFindingsAreFilteredAndCounted() {
    Finding known = finding("TNT-A01", "Query getX() has side effects");
    Finding fresh = finding("TNT-B01", "flag(boolean) is two methods");
    Baseline baseline = Baseline.of(List.of(known));

    Report filtered = baseline.apply(reportOf(List.of(known, fresh)));

    assertEquals(List.of(fresh), filtered.findings());
    assertEquals(1, filtered.stats().baselinedFindings());
  }

  @Test
  void duplicateFingerprintsConsumeTheirBudget() {
    Finding known = finding("TNT-A01", "Query getX() has side effects");
    Baseline baseline = Baseline.of(List.of(known));

    Report filtered = baseline.apply(reportOf(List.of(known, known)));

    assertEquals(1, filtered.findings().size());
    assertEquals(1, filtered.stats().baselinedFindings());
  }

  @Test
  void emptyBaselineChangesNothing() {
    Finding fresh = finding("TNT-B01", "flag(boolean) is two methods");
    Report report = reportOf(List.of(fresh));
    assertTrue(Baseline.empty().apply(report).findings().equals(report.findings()));
  }
}
