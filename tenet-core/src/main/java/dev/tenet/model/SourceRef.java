package dev.tenet.model;

import java.util.Objects;

public record SourceRef(String file, long line) implements Comparable<SourceRef> {

  public SourceRef {
    Objects.requireNonNull(file, "file");
  }

  public static final SourceRef UNKNOWN = new SourceRef("<unknown>", 0);

  @Override
  public int compareTo(SourceRef other) {
    int byFile = file.compareTo(other.file);
    return byFile != 0 ? byFile : Long.compare(line, other.line);
  }

  @Override
  public String toString() {
    return file + ":" + line;
  }
}
