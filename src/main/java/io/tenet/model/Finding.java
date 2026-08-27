package io.tenet.model;

import java.util.Comparator;
import java.util.Objects;

public record Finding(
        RuleId rule,
        Severity severity,
        String file,
        long line,
        long column,
        String message,
        String evidence) implements Comparable<Finding> {

    private static final Comparator<Finding> ORDER = Comparator
            .comparing(Finding::file)
            .thenComparingLong(Finding::line)
            .thenComparingLong(Finding::column)
            .thenComparing(finding -> finding.rule().externalId())
            .thenComparing(Finding::message);

    public Finding {
        Objects.requireNonNull(rule);
        Objects.requireNonNull(severity);
        Objects.requireNonNull(file);
        Objects.requireNonNull(message);
        evidence = evidence == null ? "" : evidence;
    }

    @Override
    public int compareTo(final Finding other) {
        return ORDER.compare(this, other);
    }
}
