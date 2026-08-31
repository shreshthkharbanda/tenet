package dev.tenet.rules.truth;

import dev.tenet.analysis.Analysis;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.model.SourceRef;
import dev.tenet.rules.Rule;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

public final class UnnamedConstantRule implements Rule {

  private static final String ID = "TNT-F02";

  private final int minOccurrences;
  private final int minFiles;
  private final RuleDescriptor descriptor;

  public UnnamedConstantRule(dev.tenet.engine.TenetConfig config) {
    this.minOccurrences = config.intParam(ID, "minOccurrences", 3);
    this.minFiles = config.intParam(ID, "minFiles", 2);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Unnamed shared constant",
            Dimension.TRUTH,
            Severity.STRONG,
            2,
            "a fact has one home",
            "Repo-wide literal index over configuration-shaped literals (separators or length >= 16 "
                + "for strings; short prose labels are not constants); "
                + minOccurrences
                + "+ occurrences across "
                + minFiles
                + "+ files.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (Map.Entry<String, List<SourceRef>> entry :
        analysis.facts().literalOccurrences().entrySet()) {
      List<SourceRef> refs = entry.getValue();
      if (!configurationShaped(entry.getKey())) continue;
      if (refs.size() < minOccurrences || fileCount(refs) < minFiles) continue;
      findings.add(finding(entry.getKey(), refs));
    }
    return findings;
  }

  private boolean configurationShaped(String literal) {
    if (!literal.startsWith("\"")) return true;
    String content = literal.substring(1, literal.length() - 1);
    return content.length() >= 16 || content.chars().anyMatch(c -> !Character.isLetter(c));
  }

  private int fileCount(List<SourceRef> refs) {
    TreeSet<String> files = new TreeSet<>();
    refs.forEach(ref -> files.add(ref.file()));
    return files.size();
  }

  private Finding finding(String literal, List<SourceRef> refs) {
    List<String> sites = refs.stream().map(SourceRef::toString).toList();
    return Finding.builder(
            descriptor.id(), "Literal " + shorten(literal) + " appears " + refs.size() + " times")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(refs.get(0))
        .witness("literal", literal)
        .witness("sites", String.join("; ", sites))
        .suggestion("name it once as a constant; every other site reads the name")
        .certificate(new Certificate.Syntactic("shared literal " + literal, refs.get(0)))
        .build();
  }

  private String shorten(String literal) {
    return literal.length() <= 32 ? literal : literal.substring(0, 29) + "...";
  }
}
