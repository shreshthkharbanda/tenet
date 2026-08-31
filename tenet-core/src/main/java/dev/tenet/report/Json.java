package dev.tenet.report;

import java.util.Locale;

final class Json {

  private Json() {}

  static String quote(String raw) {
    StringBuilder escaped = new StringBuilder("\"");
    for (char c : raw.toCharArray()) {
      switch (c) {
        case '"' -> escaped.append("\\\"");
        case '\\' -> escaped.append("\\\\");
        case '\n' -> escaped.append("\\n");
        case '\r' -> escaped.append("\\r");
        case '\t' -> escaped.append("\\t");
        default -> {
          if (c < 0x20) escaped.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
          else escaped.append(c);
        }
      }
    }
    return escaped.append('"').toString();
  }
}
