package dev.tenet.cli;

import java.io.IOException;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

final class GitChanges {

  private static final int GIT_TIMEOUT_SECONDS = 30;

  private GitChanges() {}

  static Set<String> changedFiles(Path repoDir, String baseRef) {
    Set<String> changed = new LinkedHashSet<>();
    changed.addAll(run(repoDir, "git", "diff", "--name-only", baseRef + "...HEAD"));
    changed.addAll(run(repoDir, "git", "diff", "--name-only", "HEAD"));
    changed.addAll(run(repoDir, "git", "ls-files", "--others", "--exclude-standard"));
    return changed;
  }

  private static List<String> run(Path dir, String... command) {
    try {
      Process process =
          new ProcessBuilder(command).directory(dir.toFile()).redirectErrorStream(false).start();
      String output = new String(process.getInputStream().readAllBytes());
      boolean finished = process.waitFor(GIT_TIMEOUT_SECONDS, TimeUnit.SECONDS);
      if (!finished || process.exitValue() != 0) {
        process.destroyForcibly();
        return List.of();
      }
      return output.lines().filter(line -> !line.isBlank()).toList();
    } catch (IOException e) {
      return List.of();
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      return List.of();
    }
  }
}
