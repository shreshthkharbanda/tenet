package dev.tenet.rules.names;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.TypeName;
import dev.tenet.kernel.Certificate;
import dev.tenet.model.Dimension;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.model.Severity;
import dev.tenet.rules.Rule;
import dev.tenet.rules.support.Names;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public final class VocabularyDriftRule implements Rule {

  private static final Set<String> RETRIEVAL_VERBS =
      Set.of("get", "fetch", "load", "retrieve", "find", "lookup", "read", "query");

  private static final RuleDescriptor DESCRIPTOR =
      new RuleDescriptor(
          "TNT-A04",
          "Vocabulary drift",
          Dimension.NAMES,
          Severity.ADVISORY,
          2,
          "one concept, one word, everywhere",
          "Repo-wide symbol graph: methods returning the same in-repo type grouped by retrieval "
              + "verb; two or more distinct verbs across classes is drift.");

  @Override
  public RuleDescriptor descriptor() {
    return DESCRIPTOR;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    Map<TypeName, Map<String, List<MethodFacts>>> verbsByReturnType = groupRetrievals(analysis);
    List<Finding> findings = new ArrayList<>();
    for (Map.Entry<TypeName, Map<String, List<MethodFacts>>> entry : verbsByReturnType.entrySet()) {
      if (entry.getValue().size() < 2 || !spansMultipleOwners(entry.getValue())) continue;
      findings.add(finding(entry.getKey(), entry.getValue()));
    }
    return findings;
  }

  private Map<TypeName, Map<String, List<MethodFacts>>> groupRetrievals(Analysis analysis) {
    Map<TypeName, Map<String, List<MethodFacts>>> grouped = new TreeMap<>();
    for (MethodFacts method : analysis.facts().methods().values()) {
      if (!isRetrieval(method, analysis)) continue;
      String verb = Names.verbPrefix(method.name()).toLowerCase(Locale.ROOT);
      grouped
          .computeIfAbsent(method.returnType(), key -> new LinkedHashMap<>())
          .computeIfAbsent(verb, key -> new ArrayList<>())
          .add(method);
    }
    return grouped;
  }

  private boolean isRetrieval(MethodFacts method, Analysis analysis) {
    return method.returnsValue()
        && !method.isConstructor()
        && !method.isTrivialAccessor()
        && method.visibility().isAtLeastPackage()
        && analysis.facts().isRepoType(method.returnType())
        && RETRIEVAL_VERBS.contains(Names.verbPrefix(method.name()).toLowerCase(Locale.ROOT));
  }

  private boolean spansMultipleOwners(Map<String, List<MethodFacts>> byVerb) {
    Set<TypeName> owners = new TreeSet<>();
    byVerb.values().forEach(methods -> methods.forEach(m -> owners.add(m.id().owner())));
    return owners.size() >= 2;
  }

  private Finding finding(TypeName returnType, Map<String, List<MethodFacts>> byVerb) {
    List<String> conflicting = new ArrayList<>();
    byVerb.values().forEach(methods -> methods.forEach(m -> conflicting.add(m.display())));
    MethodFacts anchor = byVerb.values().iterator().next().get(0);
    return Finding.builder(
            DESCRIPTOR.id(),
            "Vocabulary drift retrieving " + returnType.simple() + ": " + byVerb.keySet())
        .dimension(DESCRIPTOR.dimension())
        .severity(DESCRIPTOR.severity())
        .at(anchor.site())
        .witness("returnType", returnType.qualified())
        .witness("conflictingNames", String.join("; ", conflicting))
        .suggestion("pick one retrieval verb for " + returnType.simple() + " and rename the rest")
        .certificate(
            new Certificate.Syntactic(
                "retrieval verbs " + byVerb.keySet() + " for " + returnType, anchor.site()))
        .build();
  }
}
