package io.tenet.cli;

import io.tenet.analysis.JavaProjectAnalyzer;
import io.tenet.config.TenetConfig;
import io.tenet.config.TenetConfigLoader;
import io.tenet.model.AnalysisReport;
import io.tenet.model.RuleId;
import io.tenet.output.Formatters;

import java.io.IOException;
import java.io.PrintStream;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

public final class TenetMain {
    public static final String VERSION = "0.1.0";

    private TenetMain() {
    }

    public static void main(final String[] arguments) {
        System.exit(run(arguments, System.out, System.err, Path.of("").toAbsolutePath()));
    }

    public static int run(
            final String[] arguments,
            final PrintStream output,
            final PrintStream error,
            final Path workingDirectory) {
        try {
            final CliArguments cli = CliArguments.parse(arguments);
            return execute(cli, output, workingDirectory);
        } catch (final IOException | IllegalArgumentException | IllegalStateException exception) {
            error.println("tenet: " + exception.getMessage());
            return 2;
        }
    }

    private static int execute(
            final CliArguments cli,
            final PrintStream output,
            final Path workingDirectory) throws IOException {
        return switch (cli.command()) {
            case CHECK -> check(cli, output, workingDirectory);
            case EXPLAIN -> explain(cli, output);
            case VERSION -> version(output);
            case HELP -> help(output);
        };
    }

    private static int check(
            final CliArguments cli,
            final PrintStream output,
            final Path workingDirectory) throws IOException {
        final Path configPath = workingDirectory.resolve(cli.configPath()).normalize();
        TenetConfig config = TenetConfigLoader.load(configPath);
        final Map<String, String> overrides = new LinkedHashMap<>();
        if (cli.classpath() != null) {
            overrides.put("java.classpath", cli.classpath());
        }
        if (cli.release() != null) {
            overrides.put("java.release", cli.release());
        }
        if (cli.failOn() != null) {
            overrides.put("failOn", cli.failOn().name());
        }
        config = config.withOverrides(overrides);
        final AnalysisReport report = new JavaProjectAnalyzer().analyze(
                workingDirectory,
                cli.sources(),
                config);
        output.print(Formatters.formatter(cli.format()).format(report));
        return report.rejectedBy(config.failOn()) ? 1 : 0;
    }

    private static int explain(final CliArguments cli, final PrintStream output) {
        final RuleId rule = RuleId.parse(cli.rule());
        output.println(rule.externalId());
        output.println(rule.principle());
        output.println("default severity: " + rule.defaultSeverity().name().toLowerCase());
        return 0;
    }

    private static int version(final PrintStream output) {
        output.println("tenet " + VERSION);
        return 0;
    }

    private static int help(final PrintStream output) {
        output.println("Usage: tenet check [paths...] [options]");
        output.println("       tenet explain <rule-id>");
        output.println("       tenet version");
        output.println();
        output.println("Options:");
        output.println("  --config <path>       Configuration file; default tenet.properties");
        output.println("  --format <text|json|sarif>");
        output.println("  --fail-on <error|warning|never>");
        output.println("  --classpath <paths>   Compilation classpath");
        output.println("  --release <version>   Java source release");
        return 0;
    }
}
