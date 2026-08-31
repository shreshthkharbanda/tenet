package dev.tenet.engine;

import dev.tenet.model.Finding;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

public final class Baseline {

  private final Map<String, Integer> fingerprints;

  public Baseline(Map<String, Integer> fingerprints) {
    this.fingerprints = new TreeMap<>(fingerprints);
  }

  public static Baseline empty() {
    return new Baseline(Map.of());
  }

  public static Baseline of(List<Finding> findings) {
    Map<String, Integer> counts = new TreeMap<>();
    for (Finding finding : findings) {
      counts.merge(fingerprint(finding), 1, Integer::sum);
    }
    return new Baseline(counts);
  }

  public Map<String, Integer> fingerprints() {
    return Map.copyOf(fingerprints);
  }

  public boolean isEmpty() {
    return fingerprints.isEmpty();
  }

  public Report apply(Report report) {
    if (fingerprints.isEmpty()) return report;
    Map<String, Integer> budget = new HashMap<>(fingerprints);
    List<Finding> remaining = new ArrayList<>();
    int baselined = 0;
    for (Finding finding : report.findings()) {
      String print = fingerprint(finding);
      Integer left = budget.get(print);
      if (left != null && left > 0) {
        budget.put(print, left - 1);
        baselined++;
      } else {
        remaining.add(finding);
      }
    }
    return report.withFindings(remaining, report.stats().withBaselined(baselined));
  }

  public static String fingerprint(Finding finding) {
    String normalizedFile =
        finding.file().startsWith("./") ? finding.file().substring(2) : finding.file();
    String key = finding.ruleId() + "|" + normalizedFile + "|" + finding.title();
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hashed = digest.digest(key.getBytes(StandardCharsets.UTF_8));
      StringBuilder hex = new StringBuilder();
      for (int i = 0; i < 16; i++) {
        hex.append(String.format(Locale.ROOT, "%02x", hashed[i]));
      }
      return hex.toString();
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 is a mandatory JDK algorithm", e);
    }
  }
}
