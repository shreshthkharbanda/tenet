package io.tenet.output;

public final class Formatters {
    private Formatters() {
    }

    public static ReportFormatter formatter(final OutputFormat format) {
        return switch (format) {
            case TEXT -> new TextFormatter();
            case JSON -> new JsonFormatter();
            case SARIF -> new SarifFormatter();
        };
    }
}
