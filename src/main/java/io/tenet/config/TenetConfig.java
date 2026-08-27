package io.tenet.config;

import io.tenet.model.FailOn;
import io.tenet.model.RuleId;
import io.tenet.model.Severity;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

public final class TenetConfig {
    private static final Map<String, String> DEFAULTS = defaults();
    private final Map<String, String> values;
    private final RuleSettings rules;
    private final CommentSettings comments;
    private final CompilerSettings compiler;
    private final SourceSettings sources;
    private final ArchitectureSettings architecture;

    TenetConfig(final Map<String, String> values) {
        this.values = Map.copyOf(values);
        rules = new RuleSettings(this.values);
        comments = new CommentSettings(
                Pattern.compile(required(this.values, "comment.contextPattern")),
                parseInteger(this.values, "comment.maxPerFile"));
        compiler = new CompilerSettings(
                parseInteger(this.values, "java.release"),
                this.values.getOrDefault("java.classpath", "").trim());
        sources = new SourceSettings(commaSeparated(this.values, "exclude").stream()
                .map(Glob::compilePath)
                .toList());
        architecture = new ArchitectureSettings(parseBoundaries(
                this.values.getOrDefault("architecture.forbiddenDependencies", "")));
    }

    public TenetConfig withOverrides(final Map<String, String> overrides) {
        final Map<String, String> updated = new LinkedHashMap<>(values);
        updated.putAll(overrides);
        return new TenetConfig(updated);
    }

    public FailOn failOn() {
        return FailOn.parse(required(values, "failOn"));
    }

    public RuleSettings rules() {
        return rules;
    }

    public CommentSettings comments() {
        return comments;
    }

    public CompilerSettings compiler() {
        return compiler;
    }

    public SourceSettings sources() {
        return sources;
    }

    public ArchitectureSettings architecture() {
        return architecture;
    }

    static Map<String, String> defaultValues() {
        return DEFAULTS;
    }

    private static String required(final Map<String, String> values, final String key) {
        final String value = values.get(key);
        if (value == null) {
            throw new IllegalArgumentException("Missing configuration key: " + key);
        }
        return value;
    }

    private static int parseInteger(final Map<String, String> values, final String key) {
        final String value = required(values, key);
        try {
            return Integer.parseInt(value);
        } catch (final NumberFormatException exception) {
            throw new IllegalArgumentException(key + " must be an integer: " + value, exception);
        }
    }

    private static List<String> commaSeparated(final Map<String, String> values, final String key) {
        return Arrays.stream(values.getOrDefault(key, "").split(","))
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .toList();
    }

    private static List<ArchitectureBoundary> parseBoundaries(final String value) {
        final List<ArchitectureBoundary> result = new ArrayList<>();
        for (final String expression : value.split(";")) {
            if (!expression.isBlank()) {
                result.add(parseBoundary(expression));
            }
        }
        return List.copyOf(result);
    }

    private static ArchitectureBoundary parseBoundary(final String expression) {
        final String[] sides = expression.split("->", -1);
        if (sides.length != 2) {
            throw new IllegalArgumentException("Invalid architecture boundary: " + expression);
        }
        return new ArchitectureBoundary(sides[0].trim(), sides[1].trim());
    }

    private static Map<String, String> defaults() {
        final Map<String, String> defaults = new LinkedHashMap<>();
        defaults.put("failOn", "WARNING");
        defaults.put("java.release", "17");
        defaults.put("java.classpath", "");
        defaults.put("exclude", "**/build/**,**/target/**,**/generated/**,**/.gradle/**");
        defaults.put("comment.contextPattern", "^// context: [A-Za-z0-9].{8,98}\\.$");
        defaults.put("comment.maxPerFile", "1");
        defaults.put("max.fileLines", "400");
        defaults.put("max.cyclomaticComplexity", "8");
        defaults.put("max.nestingDepth", "3");
        defaults.put("max.methodLines", "30");
        defaults.put("max.parameters", "4");
        defaults.put("max.publicMethods", "7");
        defaults.put("max.interfaceMethods", "5");
        defaults.put("max.typeFanOut", "10");
        defaults.put("max.inheritanceDepth", "2");
        defaults.put("max.variantBranchSites", "1");
        defaults.put("max.responsibilityComponents", "1");
        defaults.put("min.duplicateMethodCharacters", "80");
        defaults.put("min.structuralCloneNodes", "30");
        defaults.put("architecture.forbiddenDependencies", "");
        return Map.copyOf(defaults);
    }

    public static final class RuleSettings {
        private final Map<String, String> values;

        private RuleSettings(final Map<String, String> values) {
            this.values = values;
        }

        public Severity severity(final RuleId rule) {
            final String configured = values.get("rule." + rule.externalId() + ".severity");
            if (configured == null || configured.isBlank()) {
                return rule.defaultSeverity();
            }
            return configured.equalsIgnoreCase("off") ? null : Severity.parse(configured);
        }

        public int integer(final String key) {
            return parseInteger(values, key);
        }
    }

    public record CommentSettings(Pattern allowedPattern, int maximumPerFile) {
    }

    public record CompilerSettings(int sourceRelease, String classpath) {
    }

    public static final class SourceSettings {
        private final List<Pattern> exclusions;

        private SourceSettings(final List<Pattern> exclusions) {
            this.exclusions = exclusions;
        }

        public boolean excluded(final Path relativePath) {
            final String normalized = relativePath.toString().replace('\\', '/');
            return exclusions.stream().anyMatch(pattern -> pattern.matcher(normalized).matches());
        }
    }

    public record ArchitectureSettings(List<ArchitectureBoundary> boundaries) {
        public ArchitectureSettings {
            boundaries = List.copyOf(boundaries);
        }
    }
}
