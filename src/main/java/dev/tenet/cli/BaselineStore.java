package dev.tenet.cli;

import dev.tenet.engine.Baseline;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class BaselineStore {

  static final String DEFAULT_FILE_NAME = ".tenet-baseline";
  private static final Pattern LINE = Pattern.compile("^([0-9a-f]{32}) (\\d+)$");

  private BaselineStore() {}

  static void save(Baseline baseline, Path target) throws IOException {
    StringBuilder out = new StringBuilder();
    baseline.fingerprints().entrySet().stream()
        .sorted(Map.Entry.comparingByKey())
        .forEach(entry -> out.append(entry.getKey()).append(' ').append(entry.getValue()).append('\n'));
    Files.writeString(target, out.toString());
  }

  static Baseline restore(Path source) throws IOException {
    if (!Files.isRegularFile(source)) return Baseline.empty();
    Map<String, Integer> fingerprints = new TreeMap<>();
    for (String line : Files.readAllLines(source)) {
      Matcher matcher = LINE.matcher(line.trim());
      if (matcher.matches()) {
        fingerprints.put(matcher.group(1), Integer.parseInt(matcher.group(2)));
      }
    }
    return new Baseline(fingerprints);
  }
}
