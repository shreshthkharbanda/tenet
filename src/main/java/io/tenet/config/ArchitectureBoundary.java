package io.tenet.config;

import java.util.regex.Pattern;

public record ArchitectureBoundary(String sourceExpression, String targetExpression) {
    public ArchitectureBoundary {
        if (sourceExpression.isBlank() || targetExpression.isBlank()) {
            throw new IllegalArgumentException("Architecture boundaries require non-empty source and target globs");
        }
    }

    public boolean rejects(final String sourceType, final String targetType) {
        final Pattern source = Glob.compileQualifiedName(sourceExpression);
        final Pattern target = Glob.compileQualifiedName(targetExpression);
        return source.matcher(sourceType).matches() && target.matcher(targetType).matches();
    }
}
