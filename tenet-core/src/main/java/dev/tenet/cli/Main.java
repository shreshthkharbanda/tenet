package dev.tenet.cli;

import dev.tenet.engine.Baseline;
import dev.tenet.engine.EvidenceEngine;
import dev.tenet.engine.Report;
import dev.tenet.engine.TenetConfig;
import dev.tenet.frontend.javac.JavacFrontend;
import dev.tenet.kernel.Kernel;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.report.ConsoleRenderer;
import dev.tenet.report.JsonRenderer;
import dev.tenet.report.ReportRenderer;
import dev.tenet.report.SarifRenderer;
import dev.tenet.rules.Rule;
import dev.tenet.rules.Rules;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.Callable;
import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import picocli.CommandLine.Parameters;

@Command(
    name = "tenet",
    mixinStandardHelpOptions = true,
    version = "tenet 0.1.0",
    description = "Deterministic evidence engine for Java code quality.",
    subcommands = {
      Main.CheckCommand.class,
      Main.BaselineCommand.class,
      Main.RulesCommand.class,
      Main.ExplainCommand.class
    })
public final class Main {

  public static void main(String[] args) {
    String[] effective = args.length == 0 ? new String[] {"--help"} : args;
    System.exit(new CommandLine(new Main()).execute(effective));
  }

  abstract static class AnalysisCommand {

    @Parameters(paramLabel = "PATH", description = "Source roots or files (default: current directory).")
    List<Path> paths = new ArrayList<>();

    @Option(
        names = "--classpath",
        split = ":",
        paramLabel = "JAR",
        description = "Dependency classpath. Defaults to resolving from the nearest pom.xml.")
    List<Path> classpath = new ArrayList<>();

    @Option(
        names = "--config",
        paramLabel = "FILE",
        description = "Rule configuration (default: tenet.properties in the analyzed root, then cwd).")
    Path configFile;

    @Option(
        names = "--disable",
        split = ",",
        paramLabel = "RULE",
        description = "Disable these rule ids for this run.")
    Set<String> disabledRules = new LinkedHashSet<>();

    @Option(names = "--only", split = ",", paramLabel = "RULE", description = "Run only these rule ids.")
    Set<String> onlyRules = new LinkedHashSet<>();

    List<Path> roots() {
      return paths.isEmpty() ? List.of(Path.of(".")) : paths;
    }

    Report analyze() throws IOException {
      TenetConfig config = loadConfig(roots()).withDisabled(disabledRules).withOnly(onlyRules);
      EvidenceEngine engine =
          new EvidenceEngine(new JavacFrontend(), Rules.enabled(config), new Kernel());
      return engine.check(roots(), effectiveClasspath());
    }

    Path projectDir() {
      Path first = roots().get(0).toAbsolutePath();
      Path dir = Files.isDirectory(first) ? first : first.getParent();
      for (int i = 0; i < 5 && dir != null; i++) {
        if (Files.isRegularFile(dir.resolve("pom.xml"))) return dir;
        dir = dir.getParent();
      }
      return roots().get(0).toAbsolutePath();
    }

    private List<Path> effectiveClasspath() {
      if (!classpath.isEmpty()) return classpath;
      return MavenClasspath.resolve(projectDir());
    }

    private TenetConfig loadConfig(List<Path> analyzedRoots) throws IOException {
      Path source = configFile != null ? configFile : discoverConfig(analyzedRoots);
      if (source == null) return TenetConfig.defaults();
      Properties properties = new Properties();
      try (java.io.Reader reader = Files.newBufferedReader(source)) {
        properties.load(reader);
      }
      return TenetConfig.fromProperties(properties);
    }

    private Path discoverConfig(List<Path> analyzedRoots) {
      List<Path> candidates = new ArrayList<>();
      for (Path root : analyzedRoots) {
        Path dir = Files.isDirectory(root) ? root : root.getParent();
        if (dir != null) candidates.add(dir.resolve("tenet.properties"));
      }
      candidates.add(projectDir().resolve("tenet.properties"));
      candidates.add(Path.of("tenet.properties"));
      return candidates.stream().filter(Files::isRegularFile).findFirst().orElse(null);
    }
  }

  @Command(name = "check", description = "Analyze sources and report kernel-verified findings.")
  static final class CheckCommand extends AnalysisCommand implements Callable<Integer> {

    @Option(
        names = "--format",
        defaultValue = "console",
        description = "console, json, or sarif (sarif feeds GitHub code scanning).")
    private String format;

    @Option(names = "--no-color", description = "Disable ANSI colors in console output.")
    private boolean noColor;

    @Option(
        names = "--baseline",
        paramLabel = "FILE",
        description = "Baseline of accepted findings (default: .tenet-baseline in the project root).")
    private Path baselineFile;

    @Option(names = "--no-baseline", description = "Ignore any baseline file.")
    private boolean noBaseline;

    @Option(
        names = "--fail-on",
        defaultValue = "error",
        description = "When to exit nonzero: error (default, theorem-tier only), any, or none.")
    private String failOn;

    @Option(
        names = "--changed",
        paramLabel = "BASE",
        arity = "0..1",
        fallbackValue = "origin/main",
        description = "Report only findings in files changed since BASE (default: origin/main).")
    private String changedBase;

    @Override
    public Integer call() throws Exception {
      Report report = analyze();
      if (changedBase != null) {
        report = filterToChangedFiles(report);
      }
      if (!noBaseline) {
        report = resolveBaseline().apply(report);
      }
      System.out.print(rendererFor(format).render(report));
      return switch (failOn.toLowerCase(Locale.ROOT)) {
        case "any" -> report.clean() ? 0 : 1;
        case "none" -> 0;
        default -> report.hasErrors() ? 1 : 0;
      };
    }

    private Baseline resolveBaseline() throws IOException {
      Path source =
          baselineFile != null
              ? baselineFile
              : projectDir().resolve(BaselineStore.DEFAULT_FILE_NAME);
      return BaselineStore.restore(source);
    }

    private Report filterToChangedFiles(Report report) {
      Set<String> changed = GitChanges.changedFiles(projectDir(), changedBase);
      if (changed.isEmpty()) {
        return report.withFindings(List.of(), report.stats());
      }
      List<Finding> remaining =
          report.findings().stream().filter(finding -> touches(finding, changed)).toList();
      return report.withFindings(remaining, report.stats());
    }

    private boolean touches(Finding finding, Set<String> changedPaths) {
      String file = finding.file().replace('\\', '/');
      return changedPaths.stream()
          .map(path -> path.replace('\\', '/'))
          .anyMatch(path -> file.endsWith(path) || path.endsWith(file));
    }

    private ReportRenderer rendererFor(String requested) {
      return switch (requested.toLowerCase(Locale.ROOT)) {
        case "json" -> new JsonRenderer();
        case "sarif" -> new SarifRenderer(catalogDescriptors());
        case "console" -> new ConsoleRenderer(!noColor);
        default ->
            throw new CommandLine.ParameterException(
                new CommandLine(this),
                "unknown format: " + requested + " (use console, json, or sarif)");
      };
    }
  }

  @Command(
      name = "baseline",
      description = "Record current findings as accepted debt; check then fails only on new ones.")
  static final class BaselineCommand extends AnalysisCommand implements Callable<Integer> {

    @Option(
        names = "--output",
        paramLabel = "FILE",
        description = "Where to write the baseline (default: .tenet-baseline in the project root).")
    private Path outputFile;

    @Override
    public Integer call() throws Exception {
      Report report = analyze();
      Path target =
          outputFile != null ? outputFile : projectDir().resolve(BaselineStore.DEFAULT_FILE_NAME);
      BaselineStore.save(Baseline.of(report.findings()), target);
      System.out.println(
          "Baselined "
              + report.findings().size()
              + " findings to "
              + target
              + ". New findings will now fail tenet check.");
      return 0;
    }
  }

  @Command(name = "rules", description = "List the rule catalog.")
  static final class RulesCommand implements Callable<Integer> {

    @Override
    public Integer call() {
      List<Rule> rules = new ArrayList<>(Rules.all());
      rules.sort(Comparator.comparing(rule -> rule.descriptor().id()));
      for (Rule rule : rules) {
        RuleDescriptor descriptor = rule.descriptor();
        System.out.printf(
            Locale.ROOT,
            "%-9s wave %d  %-8s  %s%n",
            descriptor.id(),
            descriptor.wave(),
            descriptor.severity().name(),
            descriptor.name());
      }
      System.out.println();
      System.out.println(rules.size() + " rules. Details: tenet explain <RULE-ID>");
      return 0;
    }
  }

  @Command(name = "explain", description = "Explain one rule: principle, mechanism, precision class.")
  static final class ExplainCommand implements Callable<Integer> {

    @Parameters(paramLabel = "RULE-ID", description = "e.g. TNT-A01")
    private String ruleId;

    @Override
    public Integer call() {
      for (Rule rule : Rules.all()) {
        RuleDescriptor descriptor = rule.descriptor();
        if (descriptor.id().equalsIgnoreCase(ruleId)) {
          System.out.println(descriptor.id() + " · " + descriptor.name());
          System.out.println(
              "dimension: " + descriptor.dimension().key + " · " + descriptor.dimension().label);
          System.out.println("severity:  " + descriptor.severity() + " (precision class)");
          System.out.println("wave:      " + descriptor.wave());
          System.out.println("principle: " + descriptor.principle());
          System.out.println("mechanism: " + descriptor.mechanism());
          return 0;
        }
      }
      System.err.println("unknown rule: " + ruleId + " (see: tenet rules)");
      return 2;
    }
  }

  static List<RuleDescriptor> catalogDescriptors() {
    return Rules.all().stream().map(Rule::descriptor).toList();
  }
}
