package dev.tenet.cli;

import dev.tenet.engine.EvidenceEngine;
import dev.tenet.engine.Report;
import dev.tenet.engine.TenetConfig;
import dev.tenet.frontend.javac.JavacFrontend;
import dev.tenet.kernel.Kernel;
import dev.tenet.model.RuleDescriptor;
import dev.tenet.report.ConsoleRenderer;
import dev.tenet.report.JsonRenderer;
import dev.tenet.report.ReportRenderer;
import dev.tenet.rules.Rule;
import dev.tenet.rules.Rules;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
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
    subcommands = {Main.CheckCommand.class, Main.RulesCommand.class, Main.ExplainCommand.class})
public final class Main {

  public static void main(String[] args) {
    String[] effective = args.length == 0 ? new String[] {"--help"} : args;
    System.exit(new CommandLine(new Main()).execute(effective));
  }

  @Command(name = "check", description = "Analyze sources and report kernel-verified findings.")
  static final class CheckCommand implements Callable<Integer> {

    @Parameters(
        paramLabel = "PATH",
        description = "Source roots or files (default: current directory).")
    private List<Path> paths = new ArrayList<>();

    @Option(
        names = "--classpath",
        split = ":",
        paramLabel = "JAR",
        description =
            "Dependency classpath; without it, unresolved calls degrade to UNKNOWN honestly.")
    private List<Path> classpath = new ArrayList<>();

    @Option(
        names = "--format",
        defaultValue = "console",
        description = "console or json (agents want json).")
    private String format;

    @Option(names = "--no-color", description = "Disable ANSI colors in console output.")
    private boolean noColor;

    @Option(
        names = "--config",
        paramLabel = "FILE",
        description =
            "Rule configuration (default: tenet.properties in the analyzed root, then cwd).")
    private Path configFile;

    @Option(
        names = "--disable",
        split = ",",
        paramLabel = "RULE",
        description = "Disable these rule ids for this run.")
    private java.util.Set<String> disabledRules = new java.util.LinkedHashSet<>();

    @Option(
        names = "--only",
        split = ",",
        paramLabel = "RULE",
        description = "Run only these rule ids.")
    private java.util.Set<String> onlyRules = new java.util.LinkedHashSet<>();

    @Override
    public Integer call() throws Exception {
      List<Path> roots = paths.isEmpty() ? List.of(Path.of(".")) : paths;
      TenetConfig config = loadConfig(roots).withDisabled(disabledRules).withOnly(onlyRules);
      EvidenceEngine engine =
          new EvidenceEngine(new JavacFrontend(), Rules.enabled(config), new Kernel());
      Report report = engine.check(roots, classpath);
      System.out.print(rendererFor(format).render(report));
      return report.clean() ? 0 : 1;
    }

    private TenetConfig loadConfig(List<Path> roots) throws java.io.IOException {
      Path source = configFile != null ? configFile : discoverConfig(roots);
      if (source == null) return TenetConfig.defaults();
      java.util.Properties properties = new java.util.Properties();
      try (java.io.Reader reader = java.nio.file.Files.newBufferedReader(source)) {
        properties.load(reader);
      }
      return TenetConfig.fromProperties(properties);
    }

    private Path discoverConfig(List<Path> roots) {
      List<Path> candidates = new java.util.ArrayList<>();
      for (Path root : roots) {
        Path dir = java.nio.file.Files.isDirectory(root) ? root : root.getParent();
        if (dir != null) candidates.add(dir.resolve("tenet.properties"));
      }
      candidates.add(Path.of("tenet.properties"));
      return candidates.stream()
          .filter(java.nio.file.Files::isRegularFile)
          .findFirst()
          .orElse(null);
    }

    private ReportRenderer rendererFor(String requested) {
      return switch (requested.toLowerCase(Locale.ROOT)) {
        case "json" -> new JsonRenderer();
        case "console" -> new ConsoleRenderer(!noColor);
        default -> throw new CommandLine.ParameterException(
            new CommandLine(this), "unknown format: " + requested + " (use console or json)");
      };
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

  @Command(
      name = "explain",
      description = "Explain one rule: principle, mechanism, precision class.")
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
}
