package dev.tenet.model;

import dev.tenet.kernel.Certificate;
import java.util.LinkedHashMap;
import java.util.Map;

public record Finding(
    String ruleId,
    String title,
    Dimension dimension,
    Severity severity,
    String file,
    long line,
    Map<String, String> witness,
    String suggestion,
    Certificate certificate) {

  public static Builder builder(String ruleId, String title) {
    return new Builder(ruleId, title);
  }

  public static final class Builder {
    private final String ruleId;
    private final String title;
    private Dimension dimension;
    private Severity severity = Severity.ADVISORY;
    private String file = "?";
    private long line;
    private final Map<String, String> witness = new LinkedHashMap<>();
    private String suggestion = "";
    private Certificate certificate;

    private Builder(String ruleId, String title) {
      this.ruleId = ruleId;
      this.title = title;
    }

    public Builder dimension(Dimension d) {
      this.dimension = d;
      return this;
    }

    public Builder severity(Severity s) {
      this.severity = s;
      return this;
    }

    public Builder at(String file, long line) {
      this.file = file;
      this.line = line;
      return this;
    }

    public Builder at(SourceRef ref) {
      return at(ref.file(), ref.line());
    }

    public Builder witness(String key, String value) {
      this.witness.put(key, value);
      return this;
    }

    public Builder suggestion(String s) {
      this.suggestion = s;
      return this;
    }

    public Builder certificate(Certificate c) {
      this.certificate = c;
      return this;
    }

    public Finding build() {
      return new Finding(
          ruleId, title, dimension, severity, file, line, witness, suggestion, certificate);
    }
  }
}
