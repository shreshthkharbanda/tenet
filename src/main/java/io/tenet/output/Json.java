package io.tenet.output;

public final class Json {
    private Json() {
    }

    public static String quote(final String value) {
        final StringBuilder output = new StringBuilder(value.length() + 2).append('"');
        value.codePoints().forEach(codePoint -> append(output, codePoint));
        return output.append('"').toString();
    }

    private static void append(final StringBuilder output, final int codePoint) {
        switch (codePoint) {
            case '"' -> output.append("\\\"");
            case '\\' -> output.append("\\\\");
            case '\b' -> output.append("\\b");
            case '\f' -> output.append("\\f");
            case '\n' -> output.append("\\n");
            case '\r' -> output.append("\\r");
            case '\t' -> output.append("\\t");
            default -> appendOrdinary(output, codePoint);
        }
    }

    private static void appendOrdinary(final StringBuilder output, final int codePoint) {
        if (codePoint < 0x20) {
            output.append(String.format("\\u%04x", codePoint));
        } else {
            output.appendCodePoint(codePoint);
        }
    }
}

