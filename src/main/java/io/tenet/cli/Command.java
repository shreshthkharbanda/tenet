package io.tenet.cli;

public enum Command {
    CHECK("check"),
    EXPLAIN("explain"),
    VERSION("version"),
    HELP("help");

    private final String token;

    Command(final String token) {
        this.token = token;
    }

    public static Command fromToken(final String token) {
        for (final Command command : values()) {
            if (command.token.equalsIgnoreCase(token)) {
                return command;
            }
        }
        return null;
    }
}
