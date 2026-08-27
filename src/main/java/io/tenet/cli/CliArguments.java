package io.tenet.cli;

import io.tenet.api.MutableState;
import io.tenet.model.FailOn;
import io.tenet.output.OutputFormat;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public record CliArguments(
        Command command,
        List<Path> sources,
        Path configPath,
        OutputFormat format,
        FailOn failOn,
        String classpath,
        String release,
        String rule) {

    public static CliArguments parse(final String[] arguments) {
        final Parser parser = new Parser(arguments);
        return parser.parse();
    }

    private static final class Parser {
        private final String[] arguments;
        private final List<Path> sources = new ArrayList<>();
        @MutableState(reason = "Advances through the immutable argument array during parsing.")
        private int index;
        @MutableState(reason = "Captures the command selected while parsing arguments.")
        private Command command = Command.CHECK;
        @MutableState(reason = "Captures the configuration path while parsing arguments.")
        private Path configPath = Path.of("tenet.properties");
        @MutableState(reason = "Captures the output format while parsing arguments.")
        private OutputFormat format = OutputFormat.TEXT;
        @MutableState(reason = "Captures the failure threshold while parsing arguments.")
        private FailOn failOn;
        @MutableState(reason = "Captures the compiler classpath while parsing arguments.")
        private String classpath;
        @MutableState(reason = "Captures the Java release while parsing arguments.")
        private String release;
        @MutableState(reason = "Captures the requested rule while parsing arguments.")
        private String rule;

        private Parser(final String[] arguments) {
            this.arguments = arguments;
        }

        private CliArguments parse() {
            parseCommand();
            while (index < arguments.length) {
                parseArgument(arguments[index]);
                index++;
            }
            if (command == Command.CHECK && sources.isEmpty()) {
                sources.add(Path.of("."));
            }
            if (command == Command.EXPLAIN && (rule == null || rule.isBlank())) {
                throw new IllegalArgumentException("explain requires a rule ID");
            }
            return new CliArguments(
                    command,
                    List.copyOf(sources),
                    configPath,
                    format,
                    failOn,
                    classpath,
                    release,
                    rule);
        }

        private void parseCommand() {
            if (arguments.length == 0 || arguments[0].startsWith("-")) {
                return;
            }
            final Command parsed = Command.fromToken(arguments[0]);
            if (parsed != null) {
                command = parsed;
                index++;
            }
            if (command == Command.EXPLAIN && index < arguments.length) {
                rule = arguments[index++];
            }
        }

        private void parseArgument(final String argument) {
            final Option option = Option.fromToken(argument);
            if (option == null) {
                parseSource(argument);
                return;
            }
            switch (option) {
                case CONFIG -> configPath = Path.of(nextValue(argument));
                case FORMAT -> format = OutputFormat.parse(nextValue(argument));
                case FAIL_ON -> failOn = FailOn.parse(nextValue(argument));
                case CLASSPATH -> classpath = nextValue(argument);
                case RELEASE -> release = nextValue(argument);
                case HELP -> command = Command.HELP;
            }
        }

        private void parseSource(final String argument) {
            if (argument.startsWith("-")) {
                throw new IllegalArgumentException("Unknown option: " + argument);
            }
            if (command != Command.CHECK) {
                throw new IllegalArgumentException("Unexpected argument: " + argument);
            }
            sources.add(Path.of(argument));
        }

        private String nextValue(final String option) {
            index++;
            if (index >= arguments.length) {
                throw new IllegalArgumentException(option + " requires a value");
            }
            return arguments[index];
        }
    }

    private enum Option {
        CONFIG("--config"),
        FORMAT("--format"),
        FAIL_ON("--fail-on"),
        CLASSPATH("--classpath"),
        RELEASE("--release"),
        HELP("--help", "-h");

        private final List<String> tokens;

        Option(final String... tokens) {
            this.tokens = List.of(tokens);
        }

        private static Option fromToken(final String token) {
            for (final Option option : values()) {
                if (option.tokens.contains(token)) {
                    return option;
                }
            }
            return null;
        }
    }
}
