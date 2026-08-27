package io.tenet.output;

public enum OutputFormat {
    TEXT,
    JSON,
    SARIF;

    public static OutputFormat parse(final String value) {
        return OutputFormat.valueOf(value.trim().toUpperCase());
    }
}

