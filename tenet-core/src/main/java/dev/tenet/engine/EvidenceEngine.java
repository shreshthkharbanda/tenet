package dev.tenet.engine;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ProgramFacts;
import dev.tenet.kernel.Kernel;
import dev.tenet.model.Finding;
import dev.tenet.rules.Rule;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public final class EvidenceEngine {

  private final Frontend frontend;
  private final List<Rule> rules;
  private final Kernel kernel;

  public EvidenceEngine(Frontend frontend, List<Rule> rules, Kernel kernel) {
    this.frontend = Objects.requireNonNull(frontend, "frontend");
    this.rules = List.copyOf(rules);
    this.kernel = Objects.requireNonNull(kernel, "kernel");
  }

  public Report check(List<Path> sourceRoots, List<Path> classpath) throws IOException {
    long started = System.nanoTime();
    ProgramFacts facts = frontend.extract(sourceRoots, classpath);
    Analysis analysis = Analysis.of(facts);

    List<Finding> verified = new ArrayList<>();
    int rejected = 0;
    int suppressed = 0;
    for (Rule rule : sortedRules()) {
      for (Finding candidate : rule.evaluate(analysis)) {
        if (!kernel.verify(candidate.certificate(), facts)) {
          rejected++;
        } else if (facts.suppressed(candidate.file(), candidate.line(), candidate.ruleId())) {
          suppressed++;
        } else {
          verified.add(candidate);
        }
      }
    }
    verified.sort(
        Comparator.comparing(Finding::file)
            .thenComparing(Finding::line)
            .thenComparing(Finding::ruleId));

    long elapsedMillis = (System.nanoTime() - started) / 1_000_000;
    Report.Stats stats =
        new Report.Stats(
            facts.fileCount(),
            facts.classes().size(),
            facts.methods().size(),
            rejected,
            suppressed,
            0,
            facts.errorCount(),
            elapsedMillis);
    return new Report(verified, stats);
  }

  private List<Rule> sortedRules() {
    List<Rule> sorted = new ArrayList<>(rules);
    sorted.sort(Comparator.comparing(rule -> rule.descriptor().id()));
    return sorted;
  }
}
