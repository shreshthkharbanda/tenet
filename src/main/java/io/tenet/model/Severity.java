package io.tenet.model;

public enum Severity {
    ERROR(2),
    WARNING(1);

    private final int rank;

    Severity(final int rank) {
        this.rank = rank;
    }

    public boolean atLeast(final Severity threshold) {
        return rank >= threshold.rank;
    }

    public static Severity parse(final String value) {
        return Severity.valueOf(value.trim().toUpperCase());
    }
}
