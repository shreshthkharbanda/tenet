package dev.tenet.cli;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

final class MavenClasspath {

  private static final int RESOLUTION_TIMEOUT_SECONDS = 120;

  private MavenClasspath() {}

  static List<Path> resolve(Path projectDir) {
    if (!Files.isRegularFile(projectDir.resolve("pom.xml"))) return List.of();
    try {
      Path outputFile = Files.createTempFile("tenet-cp", ".txt");
      Process process =
          new ProcessBuilder(
                  "mvn",
                  "-q",
                  "dependency:build-classpath",
                  "-Dmdep.outputFile=" + outputFile.toAbsolutePath(),
                  "-DincludeScope=compile")
              .directory(projectDir.toFile())
              .redirectErrorStream(true)
              .start();
      boolean finished = process.waitFor(RESOLUTION_TIMEOUT_SECONDS, TimeUnit.SECONDS);
      if (!finished || process.exitValue() != 0) {
        process.destroyForcibly();
        return List.of();
      }
      return parse(Files.readString(outputFile).trim());
    } catch (IOException e) {
      return List.of();
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      return List.of();
    }
  }

  private static List<Path> parse(String classpath) {
    List<Path> entries = new ArrayList<>();
    for (String entry : classpath.split(java.io.File.pathSeparator)) {
      if (!entry.isBlank()) entries.add(Path.of(entry));
    }
    return List.copyOf(entries);
  }
}
