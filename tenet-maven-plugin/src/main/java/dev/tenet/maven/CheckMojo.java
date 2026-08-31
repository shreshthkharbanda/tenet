package dev.tenet.maven;

import dev.tenet.engine.EvidenceEngine;
import dev.tenet.engine.Report;
import dev.tenet.engine.TenetConfig;
import dev.tenet.frontend.javac.JavacFrontend;
import dev.tenet.kernel.Kernel;
import dev.tenet.report.ConsoleRenderer;
import dev.tenet.rules.Rules;
import java.io.File;
import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;
import org.apache.maven.plugins.annotations.ResolutionScope;
import org.apache.maven.project.MavenProject;

@Mojo(
    name = "check",
    defaultPhase = LifecyclePhase.VERIFY,
    requiresDependencyResolution = ResolutionScope.COMPILE,
    threadSafe = true)
public final class CheckMojo extends AbstractMojo {

  @Parameter(defaultValue = "${project}", readonly = true, required = true)
  private MavenProject project;

  @Parameter(property = "tenet.skip", defaultValue = "false")
  private boolean skip;

  @Parameter(property = "tenet.failOnFindings", defaultValue = "true")
  private boolean failOnFindings;

  @Parameter(property = "tenet.config")
  private File configFile;

  @Override
  public void execute() throws MojoExecutionException, MojoFailureException {
    if (skip) {
      getLog().info("Tenet check skipped");
      return;
    }
    List<Path> sourceRoots = existingSourceRoots();
    if (sourceRoots.isEmpty()) {
      getLog().info("No source roots to analyze");
      return;
    }
    Report report = run(sourceRoots);
    getLog().info(System.lineSeparator() + new ConsoleRenderer(false).render(report));
    if (!report.clean() && failOnFindings) {
      throw new MojoFailureException(
          "Tenet found " + report.findings().size() + " issue(s); see the report above");
    }
  }

  private Report run(List<Path> sourceRoots) throws MojoExecutionException {
    try {
      EvidenceEngine engine =
          new EvidenceEngine(new JavacFrontend(), Rules.enabled(loadConfig()), new Kernel());
      return engine.check(sourceRoots, compileClasspath());
    } catch (IOException e) {
      throw new MojoExecutionException("Tenet analysis failed", e);
    }
  }

  private List<Path> existingSourceRoots() {
    List<Path> roots = new ArrayList<>();
    for (String root : project.getCompileSourceRoots()) {
      Path path = Path.of(root);
      if (Files.isDirectory(path)) roots.add(path);
    }
    return roots;
  }

  private List<Path> compileClasspath() throws MojoExecutionException {
    try {
      List<Path> classpath = new ArrayList<>();
      for (String element : project.getCompileClasspathElements()) {
        classpath.add(Path.of(element));
      }
      return classpath;
    } catch (org.apache.maven.artifact.DependencyResolutionRequiredException e) {
      throw new MojoExecutionException("Could not resolve compile classpath", e);
    }
  }

  private TenetConfig loadConfig() throws IOException {
    File source =
        configFile != null ? configFile : new File(project.getBasedir(), "tenet.properties");
    if (!source.isFile()) return TenetConfig.defaults();
    Properties properties = new Properties();
    try (Reader reader = Files.newBufferedReader(source.toPath())) {
      properties.load(reader);
    }
    return TenetConfig.fromProperties(properties);
  }
}
