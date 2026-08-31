package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;

public final class ProgramFacts {

  private final Map<TypeName, ClassFacts> classes;
  private final Map<MethodId, MethodFacts> methods;
  private final List<CallSite> callSites;
  private final Map<MethodId, List<CallSite>> callSitesByTarget;
  private final List<SwitchOverEnum> enumSwitches;
  private final Map<TypeName, List<SwitchOverEnum>> switchesByEnum;
  private final Map<String, List<SourceRef>> literalOccurrences;
  private final Map<String, List<MethodId>> bodyHashGroups;
  private final List<SuppressionScope> suppressions;
  private final int fileCount;
  private final int errorCount;

  private ProgramFacts(Builder b) {
    this.classes = sortedByKey(b.classes);
    this.methods = sortedByKey(b.methods);
    this.callSites = sortedCallSites(b.callSites);
    this.callSitesByTarget = groupCallSites(this.callSites);
    this.enumSwitches = sortedSwitches(b.enumSwitches);
    this.switchesByEnum = groupSwitches(this.enumSwitches);
    this.literalOccurrences = sortedLiterals(b.literalOccurrences);
    this.bodyHashGroups = groupBodyHashes(this.methods);
    this.suppressions = List.copyOf(b.suppressions);
    this.fileCount = b.fileCount;
    this.errorCount = b.errorCount;
  }

  public Map<TypeName, ClassFacts> classes() {
    return classes;
  }

  public Map<MethodId, MethodFacts> methods() {
    return methods;
  }

  public List<CallSite> callSites() {
    return callSites;
  }

  public List<SwitchOverEnum> enumSwitches() {
    return enumSwitches;
  }

  public Map<String, List<SourceRef>> literalOccurrences() {
    return literalOccurrences;
  }

  public Map<String, List<MethodId>> bodyHashGroups() {
    return bodyHashGroups;
  }

  public List<SuppressionScope> suppressions() {
    return suppressions;
  }

  public boolean suppressed(String file, long line, String ruleId) {
    return suppressions.stream().anyMatch(scope -> scope.covers(file, line, ruleId));
  }

  public int fileCount() {
    return fileCount;
  }

  public int errorCount() {
    return errorCount;
  }

  public Optional<MethodFacts> method(MethodId id) {
    return Optional.ofNullable(methods.get(id));
  }

  public Optional<ClassFacts> classOf(TypeName name) {
    return Optional.ofNullable(classes.get(name));
  }

  public boolean isRepoType(TypeName name) {
    return classes.containsKey(name);
  }

  public List<CallSite> callSitesOf(MethodId target) {
    return callSitesByTarget.getOrDefault(target, List.of());
  }

  public List<SwitchOverEnum> switchesOver(TypeName enumType) {
    return switchesByEnum.getOrDefault(enumType, List.of());
  }

  public List<MethodFacts> methodsOf(ClassFacts cls) {
    List<MethodFacts> result = new ArrayList<>();
    for (MethodId id : cls.methods()) {
      MethodFacts m = methods.get(id);
      if (m != null) result.add(m);
    }
    return List.copyOf(result);
  }

  public static Builder builder() {
    return new Builder();
  }

  private static <K extends Comparable<K>, V> Map<K, V> sortedByKey(Map<K, V> source) {
    Map<K, V> sorted = new TreeMap<>(source);
    return java.util.Collections.unmodifiableMap(new LinkedHashMap<>(sorted));
  }

  private static List<CallSite> sortedCallSites(List<CallSite> sites) {
    List<CallSite> sorted = new ArrayList<>(sites);
    sorted.sort(Comparator.comparing(CallSite::site).thenComparing(CallSite::target));
    return List.copyOf(sorted);
  }

  private static Map<MethodId, List<CallSite>> groupCallSites(List<CallSite> sites) {
    Map<MethodId, List<CallSite>> grouped = new TreeMap<>();
    for (CallSite s : sites) {
      grouped.computeIfAbsent(s.target(), key -> new ArrayList<>()).add(s);
    }
    grouped.replaceAll((key, value) -> List.copyOf(value));
    return java.util.Collections.unmodifiableMap(new LinkedHashMap<>(grouped));
  }

  private static List<SwitchOverEnum> sortedSwitches(List<SwitchOverEnum> switches) {
    List<SwitchOverEnum> sorted = new ArrayList<>(switches);
    sorted.sort(Comparator.comparing(SwitchOverEnum::site));
    return List.copyOf(sorted);
  }

  private static Map<TypeName, List<SwitchOverEnum>> groupSwitches(List<SwitchOverEnum> switches) {
    Map<TypeName, List<SwitchOverEnum>> grouped = new TreeMap<>();
    for (SwitchOverEnum s : switches) {
      grouped.computeIfAbsent(s.enumType(), key -> new ArrayList<>()).add(s);
    }
    grouped.replaceAll((key, value) -> List.copyOf(value));
    return java.util.Collections.unmodifiableMap(new LinkedHashMap<>(grouped));
  }

  private static Map<String, List<SourceRef>> sortedLiterals(
      Map<String, List<SourceRef>> literals) {
    Map<String, List<SourceRef>> sorted = new TreeMap<>();
    for (Map.Entry<String, List<SourceRef>> entry : literals.entrySet()) {
      List<SourceRef> refs = new ArrayList<>(entry.getValue());
      refs.sort(Comparator.naturalOrder());
      sorted.put(entry.getKey(), List.copyOf(refs));
    }
    return java.util.Collections.unmodifiableMap(new LinkedHashMap<>(sorted));
  }

  private static Map<String, List<MethodId>> groupBodyHashes(Map<MethodId, MethodFacts> methods) {
    Map<String, List<MethodId>> grouped = new TreeMap<>();
    for (MethodFacts m : methods.values()) {
      m.bodyHash()
          .ifPresent(hash -> grouped.computeIfAbsent(hash, key -> new ArrayList<>()).add(m.id()));
    }
    grouped.replaceAll((key, value) -> List.copyOf(value));
    return java.util.Collections.unmodifiableMap(new LinkedHashMap<>(grouped));
  }

  public static final class Builder {
    private final Map<TypeName, ClassFacts> classes = new LinkedHashMap<>();
    private final Map<MethodId, MethodFacts> methods = new LinkedHashMap<>();
    private final List<CallSite> callSites = new ArrayList<>();
    private final List<SwitchOverEnum> enumSwitches = new ArrayList<>();
    private final Map<String, List<SourceRef>> literalOccurrences = new LinkedHashMap<>();
    private final List<SuppressionScope> suppressions = new ArrayList<>();
    private int fileCount;
    private int errorCount;

    private Builder() {}

    public Builder addClass(ClassFacts c) {
      this.classes.put(c.name(), c);
      return this;
    }

    public Builder addMethod(MethodFacts m) {
      this.methods.put(m.id(), m);
      return this;
    }

    public Builder addCallSite(CallSite s) {
      this.callSites.add(s);
      return this;
    }

    public Builder addEnumSwitch(SwitchOverEnum s) {
      this.enumSwitches.add(s);
      return this;
    }

    public Builder addSuppression(SuppressionScope scope) {
      this.suppressions.add(scope);
      return this;
    }

    public Builder fileCount(int v) {
      this.fileCount = v;
      return this;
    }

    public Builder errorCount(int v) {
      this.errorCount = v;
      return this;
    }

    public Builder addLiteral(String value, SourceRef site) {
      this.literalOccurrences.computeIfAbsent(value, key -> new ArrayList<>()).add(site);
      return this;
    }

    public ProgramFacts build() {
      return new ProgramFacts(this);
    }
  }
}
