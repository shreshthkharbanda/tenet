package io.tenet.model;

public enum FailOn {
    ERROR,
    WARNING,
    NEVER;

    public boolean rejects(final Severity severity) {
        return switch (this) {
            case ERROR -> severity == Severity.ERROR;
            case WARNING -> true;
            case NEVER -> false;
        };
    }

    public static FailOn parse(final String value) {
        return FailOn.valueOf(value.trim().toUpperCase());
    }
}
