package dev.tenet.frontend.javac;

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import dev.tenet.engine.Frontend;
import dev.tenet.facts.ProgramFacts;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class JavacFrontend implements Frontend {

  @Override
  public ProgramFacts extract(List<Path> sourceRoots, List<Path> classpath) throws IOException {
    List<Path> files = SourceScanner.scan(sourceRoots);
    if (files.isEmpty()) {
      return ProgramFacts.builder().build();
    }
    JavaCompiler compiler =
        Objects.requireNonNull(
            ToolProvider.getSystemJavaCompiler(), "run Tenet on a JDK, not a JRE");
    DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
    try (StandardJavaFileManager fileManager =
        compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8)) {
      if (!classpath.isEmpty()) {
        fileManager.setLocationFromPaths(StandardLocation.CLASS_PATH, classpath);
      }
      Iterable<? extends JavaFileObject> units = fileManager.getJavaFileObjectsFromPaths(files);
      JavacTask task =
          (JavacTask)
              compiler.getTask(
                  null, fileManager, diagnostics, List.of("-proc:none", "-nowarn"), null, units);
      return runExtraction(task, files.size(), diagnostics);
    }
  }

  private ProgramFacts runExtraction(
      JavacTask task, int fileCount, DiagnosticCollector<JavaFileObject> diagnostics)
      throws IOException {
    List<CompilationUnitTree> parsed = new ArrayList<>();
    task.parse().forEach(parsed::add);
    task.analyze();

    Trees trees = Trees.instance(task);
    Ids ids = new Ids(task.getTypes());
    Set<String> repoTypeNames = declaredTypeNames(parsed, trees);

    ProgramFacts.Builder program =
        ProgramFacts.builder().fileCount(fileCount).errorCount(countErrors(diagnostics));
    FactsCollector collector = new FactsCollector(trees, ids, repoTypeNames, program);
    for (CompilationUnitTree unit : parsed) {
      collector.collect(unit);
    }
    return program.build();
  }

  private Set<String> declaredTypeNames(List<CompilationUnitTree> parsed, Trees trees) {
    Set<String> names = new LinkedHashSet<>();
    TreePathScanner<Void, Void> scanner =
        new TreePathScanner<>() {
          @Override
          public Void visitClass(ClassTree tree, Void unused) {
            Element element = trees.getElement(getCurrentPath());
            if (element instanceof TypeElement type) {
              names.add(type.getQualifiedName().toString());
            }
            return super.visitClass(tree, unused);
          }
        };
    for (CompilationUnitTree unit : parsed) {
      scanner.scan(unit, null);
    }
    return names;
  }

  private int countErrors(DiagnosticCollector<JavaFileObject> diagnostics) {
    int errors = 0;
    for (Diagnostic<? extends JavaFileObject> diagnostic : diagnostics.getDiagnostics()) {
      if (diagnostic.getKind() == Diagnostic.Kind.ERROR) errors++;
    }
    return errors;
  }
}
