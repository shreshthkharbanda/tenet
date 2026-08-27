package io.tenet.config;

import java.util.regex.Pattern;

public final class Glob {
    private Glob() {
    }

    public static Pattern compilePath(final String glob) {
        final String normalized = glob.replace('\\', '/');
        final StringBuilder regex = new StringBuilder("^");
        for (int index = 0; index < normalized.length(); index++) {
            index = appendPathToken(regex, normalized, index);
        }
        return Pattern.compile(regex.append('$').toString());
    }

    private static int appendPathToken(
            final StringBuilder regex,
            final String glob,
            final int index) {
        final char current = glob.charAt(index);
        if (current == '*') {
            return appendPathStar(regex, glob, index);
        }
        if (current == '?') {
            regex.append("[^/]");
        } else {
            appendEscaped(regex, current);
        }
        return index;
    }

    private static int appendPathStar(
            final StringBuilder regex,
            final String glob,
            final int index) {
        if (!hasCharacter(glob, index + 1, '*')) {
            regex.append("[^/]*");
            return index;
        }
        if (hasCharacter(glob, index + 2, '/')) {
            regex.append("(?:.*/)?");
            return index + 2;
        }
        regex.append(".*");
        return index + 1;
    }

    private static boolean hasCharacter(final String value, final int index, final char expected) {
        return index < value.length() && value.charAt(index) == expected;
    }

    public static Pattern compileQualifiedName(final String glob) {
        final StringBuilder regex = new StringBuilder("^");
        for (int index = 0; index < glob.length(); index++) {
            final char current = glob.charAt(index);
            if (current == '*') {
                final boolean doubleStar = index + 1 < glob.length() && glob.charAt(index + 1) == '*';
                regex.append(doubleStar ? ".*" : "[^.]*");
                index += doubleStar ? 1 : 0;
            } else {
                appendEscaped(regex, current);
            }
        }
        return Pattern.compile(regex.append('$').toString());
    }

    private static void appendEscaped(final StringBuilder target, final char value) {
        if ("\\.^$|()[]{}+".indexOf(value) >= 0) {
            target.append('\\');
        }
        target.append(value);
    }
}
