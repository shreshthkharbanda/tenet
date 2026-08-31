package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertTrue;

import dev.tenet.engine.EvidenceEngine;
import dev.tenet.engine.Report;
import dev.tenet.frontend.javac.JavacFrontend;
import dev.tenet.kernel.Kernel;
import dev.tenet.model.Finding;
import dev.tenet.rules.Rules;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class DogfoodTest {

  @Test
  void tenetIsCleanByItsOwnStandard() throws Exception {
    EvidenceEngine engine = new EvidenceEngine(new JavacFrontend(), Rules.all(), new Kernel());
    Report report = engine.check(List.of(Path.of("src", "main", "java")), runtimeClasspath());

    StringBuilder details = new StringBuilder();
    for (Finding finding : report.findings()) {
      details
          .append('\n')
          .append(finding.ruleId())
          .append(' ')
          .append(finding.title())
          .append(" @ ")
          .append(finding.file())
          .append(':')
          .append(finding.line());
    }
    assertTrue(report.clean(), "Tenet flagged its own code:" + details);
  }

  private List<Path> runtimeClasspath() {
    List<Path> classpath = new ArrayList<>();
    for (String entry : System.getProperty("java.class.path").split(java.io.File.pathSeparator)) {
      if (!entry.isBlank()) classpath.add(Path.of(entry));
    }
    return classpath;
  }
}
