package dev.tenet.frontend.javac;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

final class SourceScanner {

  private static final Set<String> EXCLUDED_DIRS =
      Set.of("target", "build", ".git", ".idea", "node_modules", "out");

  private SourceScanner() {}

  static List<Path> scan(List<Path> roots) throws IOException {
    List<Path> files = new ArrayList<>();
    for (Path root : roots) {
      collectFrom(root, files);
    }
    files.sort(Comparator.comparing(Path::toString));
    return files;
  }

  private static void collectFrom(Path root, List<Path> files) throws IOException {
    if (Files.isRegularFile(root)) {
      if (isSource(root)) files.add(root);
      return;
    }
    if (!Files.isDirectory(root)) return;
    Files.walkFileTree(
        root,
        new SimpleFileVisitor<>() {
          @Override
          public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
            String name = dir.getFileName() == null ? "" : dir.getFileName().toString();
            boolean excluded = EXCLUDED_DIRS.contains(name) || name.startsWith("generated");
            return excluded ? FileVisitResult.SKIP_SUBTREE : FileVisitResult.CONTINUE;
          }

          @Override
          public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
            if (isSource(file)) files.add(file);
            return FileVisitResult.CONTINUE;
          }
        });
  }

  private static boolean isSource(Path file) {
    String name = file.getFileName().toString();
    return name.endsWith(".java")
        && !name.equals("module-info.java")
        && !name.equals("package-info.java");
  }
}
