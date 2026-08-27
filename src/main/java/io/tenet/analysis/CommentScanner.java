package io.tenet.analysis;

import io.tenet.api.MutableState;
import io.tenet.config.TenetConfig;
import io.tenet.model.RuleId;

import java.util.regex.Pattern;

public final class CommentScanner {
    private final JavaSource source;
    private final TenetConfig config;
    private final ProjectFacts facts;
    private final Pattern allowedPattern;
    @MutableState(reason = "Tracks the current lexical line during one scan.")
    private int line = 1;
    @MutableState(reason = "Tracks the current lexical column during one scan.")
    private int column = 1;
    @MutableState(reason = "Counts accepted context records during one scan.")
    private int contextComments;

    public CommentScanner(final JavaSource source, final TenetConfig config, final ProjectFacts facts) {
        this.source = source;
        this.config = config;
        this.facts = facts;
        allowedPattern = config.comments().allowedPattern();
    }

    public void scan() {
        final String content = source.content();
        int index = 0;
        Mode mode = Mode.NORMAL;
        while (index < content.length()) {
            final Step step = scanToken(mode, index);
            mode = step.mode();
            index = step.index();
        }
    }

    private Step scanToken(final Mode mode, final int index) {
        return switch (mode) {
            case NORMAL -> scanNormal(index);
            case STRING -> scanQuoted(index, '"', Mode.STRING);
            case CHARACTER -> scanQuoted(index, '\'', Mode.CHARACTER);
            case TEXT_BLOCK -> scanTextBlock(index);
        };
    }

    private Step scanNormal(final int index) {
        final String content = source.content();
        final char current = content.charAt(index);
        if (content.startsWith("//", index)) {
            return new Step(Mode.NORMAL, scanLineComment(index));
        }
        if (content.startsWith("/*", index)) {
            return new Step(Mode.NORMAL, scanBlockComment(index));
        }
        if (startsTextBlock(content, index)) {
            return new Step(Mode.TEXT_BLOCK, advanceTextBlockDelimiter(index));
        }
        if (current == '"') {
            return new Step(Mode.STRING, advance(current, index));
        }
        if (current == '\'') {
            return new Step(Mode.CHARACTER, advance(current, index));
        }
        return new Step(Mode.NORMAL, advance(current, index));
    }

    private Step scanQuoted(final int index, final char delimiter, final Mode activeMode) {
        final char current = source.content().charAt(index);
        final Mode nextMode = current == delimiter && !escaped(source.content(), index) ? Mode.NORMAL : activeMode;
        return new Step(nextMode, advance(current, index));
    }

    private Step scanTextBlock(final int index) {
        if (startsTextBlock(source.content(), index)) {
            return new Step(Mode.NORMAL, advanceTextBlockDelimiter(index));
        }
        final char current = source.content().charAt(index);
        return new Step(Mode.TEXT_BLOCK, advance(current, index));
    }

    private int scanLineComment(final int start) {
        final int commentLine = line;
        final int commentColumn = column;
        final int end = findLineEnd(start);
        final String comment = source.content().substring(start, end).trim();
        validateLineComment(comment, new Location(commentLine, commentColumn));
        consume(start, end);
        return end;
    }

    private void validateLineComment(final String comment, final Location location) {
        if (allowedPattern.matcher(comment).matches()) {
            acceptContextComment(location);
            return;
        }
        facts.add(new Violation(
                RuleId.COMMENT,
                source,
                location,
                "Remove the comment or encode the reason as `// context: <reason>.`",
                "comment=" + abbreviate(comment)));
    }

    private void acceptContextComment(final Location location) {
        contextComments++;
        final int maximum = config.comments().maximumPerFile();
        if (contextComments > maximum) {
            facts.add(new Violation(
                    RuleId.COMMENT,
                    source,
                    location,
                    "A source file may contain at most " + maximum + " context comment",
                    "context comments=" + contextComments));
        }
    }

    private int scanBlockComment(final int start) {
        final int commentLine = line;
        final int commentColumn = column;
        final int end = findBlockEnd(start);
        final boolean closed = end <= source.content().length() && end >= 2
                && source.content().substring(end - 2, end).equals("*/");
        consume(start, end);
        facts.add(new Violation(
                RuleId.COMMENT,
                source,
                new Location(commentLine, commentColumn),
                "Block and Javadoc comments are forbidden",
                closed ? "block comment" : "unterminated block comment"));
        return end;
    }

    private int findLineEnd(final int start) {
        int end = start;
        while (end < source.content().length()
                && source.content().charAt(end) != '\n'
                && source.content().charAt(end) != '\r') {
            end++;
        }
        return end;
    }

    private int findBlockEnd(final int start) {
        final int closing = source.content().indexOf("*/", start + 2);
        return closing < 0 ? source.content().length() : closing + 2;
    }

    private void consume(final int start, final int end) {
        int cursor = start;
        while (cursor < end) {
            cursor = advance(source.content().charAt(cursor), cursor);
        }
    }

    private int advanceTextBlockDelimiter(final int index) {
        int nextIndex = index;
        for (int count = 0; count < 3; count++) {
            nextIndex = advance('"', nextIndex);
        }
        return nextIndex;
    }

    private int advance(final char value, final int index) {
        if (value == '\n') {
            line++;
            column = 1;
        } else {
            column++;
        }
        return index + 1;
    }

    private static boolean startsTextBlock(final String content, final int index) {
        return index + 2 < content.length()
                && content.charAt(index) == '"'
                && content.charAt(index + 1) == '"'
                && content.charAt(index + 2) == '"';
    }

    private static boolean escaped(final String content, final int index) {
        int slashes = 0;
        for (int cursor = index - 1; cursor >= 0 && content.charAt(cursor) == '\\'; cursor--) {
            slashes++;
        }
        return slashes % 2 == 1;
    }

    private static String abbreviate(final String value) {
        return value.length() <= 80 ? value : value.substring(0, 77) + "...";
    }

    private enum Mode {
        NORMAL,
        STRING,
        CHARACTER,
        TEXT_BLOCK
    }

    private record Step(Mode mode, int index) {
    }
}
