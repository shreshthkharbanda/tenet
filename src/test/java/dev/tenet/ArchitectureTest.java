package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class ArchitectureTest {

  private static final Path MAIN_SOURCES = Path.of("src", "main", "java", "dev", "tenet");
  private static final List<String> COMPILER_IMPORTS =
      List.of("import com.sun.", "import javax.tools.", "import javax.lang.model.");
  private static final List<String> ADAPTER_IMPORTS =
      List.of("import dev.tenet.frontend.", "import dev.tenet.report.", "import dev.tenet.cli.");
  private static final List<String> DOMAIN_PACKAGES =
      List.of("model", "facts", "analysis", "kernel", "rules", "engine");

  @Test
  void onlyTheJavacAdapterImportsCompilerApis() throws IOException {
    List<String> offenders = new ArrayList<>();
    forEachSource(
        (path, content) -> {
          boolean insideAdapter = path.toString().contains("frontend");
          if (!insideAdapter && COMPILER_IMPORTS.stream().anyMatch(content::contains)) {
            offenders.add(path.toString());
          }
        });
    assertTrue(
        offenders.isEmpty(), "compiler API leaked outside the frontend adapter: " + offenders);
  }

  @Test
  void domainPackagesNeverDependOnAdapters() throws IOException {
    List<String> offenders = new ArrayList<>();
    forEachSource(
        (path, content) -> {
          boolean inDomain =
              DOMAIN_PACKAGES.stream().anyMatch(pkg -> path.startsWith(MAIN_SOURCES.resolve(pkg)));
          if (inDomain && ADAPTER_IMPORTS.stream().anyMatch(content::contains)) {
            offenders.add(path.toString());
          }
        });
    assertTrue(offenders.isEmpty(), "domain depends on an adapter: " + offenders);
  }

  private void forEachSource(SourceCheck check) throws IOException {
    try (Stream<Path> paths = Files.walk(MAIN_SOURCES)) {
      for (Path path : paths.filter(p -> p.toString().endsWith(".java")).toList()) {
        check.inspect(path, Files.readString(path));
      }
    }
  }

  private interface SourceCheck {
    void inspect(Path path, String content) throws IOException;
  }
}
