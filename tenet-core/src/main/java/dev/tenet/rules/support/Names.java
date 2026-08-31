package dev.tenet.rules.support;

import java.util.Locale;
import java.util.Set;

public final class Names {

  private static final Set<String> QUERY_VERBS =
      Set.of(
          "get", "is", "has", "find", "fetch", "load", "lookup", "peek", "query", "count",
          "compute", "list", "read");

  private static final Set<String> COMMAND_VERBS =
      Set.of(
          "add",
          "remove",
          "put",
          "set",
          "push",
          "pop",
          "poll",
          "take",
          "offer",
          "register",
          "save",
          "update",
          "delete",
          "create",
          "insert",
          "append",
          "clear",
          "reset",
          "mark",
          "record",
          "increment",
          "decrement",
          "publish",
          "send",
          "write",
          "close",
          "open",
          "start",
          "stop",
          "run",
          "execute",
          "apply",
          "accept",
          "flush",
          "drain");

  private static final Set<String> PREDICATE_PREFIXES =
      Set.of(
          "is",
          "has",
          "can",
          "should",
          "was",
          "were",
          "will",
          "did",
          "does",
          "are",
          "needs",
          "allows",
          "supports",
          "contains",
          "matches",
          "exists");

  private static final Set<String> PREDICATE_WORDS =
      Set.of(
          "enabled",
          "disabled",
          "visible",
          "active",
          "valid",
          "required",
          "ready",
          "empty",
          "present",
          "found",
          "ok",
          "done",
          "open",
          "closed",
          "bounded",
          "proven",
          "clean");

  private static final Set<String> VAGUE_LEMMAS =
      Set.of(
          "data",
          "info",
          "temp",
          "tmp",
          "obj",
          "stuff",
          "thing",
          "misc",
          "foo",
          "bar",
          "dummy",
          "helper",
          "manager",
          "handler2",
          "process",
          "util");

  private Names() {}

  public static boolean startsWithQueryVerb(String name) {
    return startsWithAny(name, QUERY_VERBS);
  }

  public static boolean startsWithCommandVerb(String name) {
    return startsWithAny(name, COMMAND_VERBS);
  }

  public static boolean readsAsPredicate(String name) {
    if (PREDICATE_WORDS.contains(name.toLowerCase(Locale.ROOT))) return true;
    return startsWithAny(name, PREDICATE_PREFIXES);
  }

  public static boolean isVague(String name) {
    String lower = name.toLowerCase(Locale.ROOT);
    String stripped = lower.replaceAll("\\d+$", "");
    if (VAGUE_LEMMAS.contains(stripped)) return true;
    return lower.matches("(data|info|result|temp|obj)\\d+");
  }

  public static String verbPrefix(String name) {
    for (int i = 1; i < name.length(); i++) {
      if (Character.isUpperCase(name.charAt(i))) return name.substring(0, i);
    }
    return name;
  }

  private static boolean startsWithAny(String name, Set<String> prefixes) {
    String prefix = verbPrefix(name).toLowerCase(Locale.ROOT);
    return prefixes.contains(prefix);
  }
}
