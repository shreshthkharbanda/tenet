package dev.tenet.rules.design;

import dev.tenet.analysis.Analysis;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.FieldFacts;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
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
import java.util.Set;
import java.util.TreeSet;

public final class SplitBrainClassRule implements Rule {

  private static final String ID = "TNT-G01";

  private final int minMembers;
  private final RuleDescriptor descriptor;

  public SplitBrainClassRule(dev.tenet.engine.TenetConfig config) {
    this.minMembers = config.intParam(ID, "minMembers", 6);
    this.descriptor =
        new RuleDescriptor(
            ID,
            "Split-brain class",
            Dimension.DESIGN,
            Severity.STRONG,
            2,
            "single responsibility, measured",
            "LCOM4 cohesion graph: methods and instance fields as nodes, accesses and internal "
                + "calls as edges; two or more connected components is a proven partition. "
                + "Immutable aggregates and Builders exempt — their cohesion lives in construction.");
  }

  @Override
  public RuleDescriptor descriptor() {
    return descriptor;
  }

  @Override
  public List<Finding> evaluate(Analysis analysis) {
    List<Finding> findings = new ArrayList<>();
    for (ClassFacts cls : analysis.facts().classes().values()) {
      if (!eligible(cls)) continue;
      List<Set<String>> components = components(cls, analysis);
      if (components.size() >= 2) {
        findings.add(finding(cls, components));
      }
    }
    return findings;
  }

  private boolean eligible(ClassFacts cls) {
    boolean hasMutableField = cls.instanceFields().stream().anyMatch(f -> !f.isFinal());
    return cls.kind() == ClassFacts.Kind.CLASS
        && hasMutableField
        && !cls.name().simple().endsWith("Builder");
  }

  private List<Set<String>> components(ClassFacts cls, Analysis analysis) {
    Map<String, String> parents = new LinkedHashMap<>();
    for (FieldFacts field : cls.instanceFields()) {
      parents.put(field.id().name(), field.id().name());
    }
    List<MethodFacts> methods = new ArrayList<>();
    for (MethodFacts method : analysis.facts().methodsOf(cls)) {
      if (method.isConstructor() || method.isStatic()) continue;
      methods.add(method);
      parents.put(method.name(), method.name());
    }
    if (parents.size() < minMembers) return List.of();

    UnionFind unionFind = new UnionFind(parents);
    for (MethodFacts method : methods) {
      method.ownFieldsAccessed().forEach(field -> unionFind.union(method.name(), field));
      for (MethodId callee : method.callees()) {
        if (callee.owner().equals(cls.name()) && isGraphNode(callee, analysis)) {
          unionFind.union(method.name(), callee.name());
        }
      }
    }
    return unionFind.components();
  }

  private boolean isGraphNode(MethodId callee, Analysis analysis) {
    return analysis
        .facts()
        .method(callee)
        .map(m -> !m.isStatic() && !m.isConstructor())
        .orElse(false);
  }

  private Finding finding(ClassFacts cls, List<Set<String>> components) {
    List<String> summaries = new ArrayList<>();
    components.forEach(component -> summaries.add(component.toString()));
    return Finding.builder(
            descriptor.id(),
            cls.name().simple() + " is " + components.size() + " classes sharing a name")
        .dimension(descriptor.dimension())
        .severity(descriptor.severity())
        .at(cls.site())
        .witness("components", String.join(" | ", summaries))
        .witness("proof", "no field access or internal call crosses the partition")
        .suggestion("split along the components; each island is a class that wants its own name")
        .certificate(new Certificate.Partition(cls.name(), components))
        .build();
  }

  private static final class UnionFind {
    private final Map<String, String> parents;

    private UnionFind(Map<String, String> parents) {
      this.parents = new LinkedHashMap<>(parents);
    }

    private void union(String left, String right) {
      if (!parents.containsKey(left) || !parents.containsKey(right)) return;
      parents.put(find(left), find(right));
    }

    private String find(String member) {
      String root = member;
      while (!parents.get(root).equals(root)) {
        root = parents.get(root);
      }
      return root;
    }

    private List<Set<String>> components() {
      Map<String, Set<String>> byRoot = new LinkedHashMap<>();
      for (String member : parents.keySet()) {
        byRoot.computeIfAbsent(find(member), key -> new TreeSet<>()).add(member);
      }
      return List.copyOf(byRoot.values());
    }
  }
}
