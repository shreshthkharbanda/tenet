package dev.tenet.frontend.javac;

import dev.tenet.facts.ExternalCall;
import java.util.List;

final class ExternalCallClassifier {

  private static final List<String> IO_PREFIXES =
      List.of(
          "java.io.",
          "java.nio.",
          "java.net.",
          "java.sql.",
          "javax.sql.",
          "software.amazon.awssdk",
          "com.amazonaws",
          "okhttp3",
          "org.apache.http",
          "org.apache.kafka",
          "redis.clients",
          "com.mongodb",
          "io.lettuce",
          "jakarta.persistence",
          "javax.persistence",
          "org.hibernate",
          "java.rmi.");

  private static final List<String> LOGGING_PREFIXES =
      List.of(
          "org.slf4j",
          "org.apache.logging",
          "org.apache.log4j",
          "java.util.logging",
          "ch.qos.logback",
          "com.google.common.flogger");

  private static final List<String> PURE_PREFIXES =
      List.of(
          "java.lang.Math",
          "java.lang.StrictMath",
          "java.lang.String",
          "java.lang.Character",
          "java.lang.Boolean",
          "java.lang.Byte",
          "java.lang.Short",
          "java.lang.Integer",
          "java.lang.Long",
          "java.lang.Float",
          "java.lang.Double",
          "java.lang.Enum",
          "java.lang.Object",
          "java.lang.Iterable",
          "java.lang.Comparable",
          "java.lang.CharSequence",
          "java.util.Objects",
          "java.util.Optional",
          "java.util.Arrays",
          "java.util.Comparator",
          "java.util.regex.",
          "java.util.stream.",
          "java.util.Collections",
          "java.util.List",
          "java.util.Map",
          "java.util.Set",
          "java.util.Collection",
          "java.util.Iterator",
          "java.util.Spliterator",
          "java.time.Duration",
          "java.time.Instant",
          "java.time.LocalDate",
          "java.math.BigDecimal",
          "java.math.BigInteger",
          "java.util.UUID",
          "java.util.OptionalInt",
          "java.util.function.");

  private static final List<String> LOCAL_PREFIXES =
      List.of(
          "java.lang.StringBuilder",
          "java.lang.StringBuffer",
          "java.util.ArrayList",
          "java.util.HashMap",
          "java.util.HashSet",
          "java.util.LinkedList",
          "java.util.ArrayDeque",
          "java.util.TreeMap",
          "java.util.TreeSet",
          "java.util.LinkedHashMap",
          "java.util.LinkedHashSet",
          "java.util.StringJoiner",
          "java.util.EnumMap");

  private ExternalCallClassifier() {}

  static ExternalCall.EffectClass classify(String ownerQName, String methodName) {
    if (ownerQName == null) return ExternalCall.EffectClass.UNKNOWN;
    if (readsClock(methodName)) return ExternalCall.EffectClass.UNKNOWN;
    if (readsEnvironment(ownerQName, methodName)) return ExternalCall.EffectClass.UNKNOWN;
    if (isThreadConfined(ownerQName)) return ExternalCall.EffectClass.LOCAL_MUTATION;
    if (isInMemoryNio(ownerQName)) return ExternalCall.EffectClass.LOCAL_MUTATION;
    if (isSystemLevel(ownerQName)) return ExternalCall.EffectClass.IO;
    if (matchesAny(ownerQName, LOGGING_PREFIXES)) return ExternalCall.EffectClass.LOGGING;
    if (matchesAny(ownerQName, IO_PREFIXES)) return ExternalCall.EffectClass.IO;
    if (matchesAny(ownerQName, LOCAL_PREFIXES)) return ExternalCall.EffectClass.LOCAL_MUTATION;
    if (matchesAny(ownerQName, PURE_PREFIXES)) return ExternalCall.EffectClass.PURE;
    return ExternalCall.EffectClass.UNKNOWN;
  }

  static boolean isInfrastructureType(String qname) {
    return qname != null && matchesAny(qname, IO_PREFIXES);
  }

  private static boolean isInMemoryNio(String ownerQName) {
    return ownerQName.startsWith("java.nio.")
        && !ownerQName.startsWith("java.nio.file")
        && !ownerQName.startsWith("java.nio.channels");
  }

  private static boolean readsClock(String methodName) {
    return methodName.equals("now")
        || methodName.equals("currentTimeMillis")
        || methodName.equals("nanoTime");
  }

  private static boolean isSystemLevel(String ownerQName) {
    return ownerQName.equals("java.lang.System")
        || ownerQName.equals("java.lang.Thread")
        || ownerQName.startsWith("java.lang.Thread$")
        || ownerQName.startsWith("java.lang.Process")
        || ownerQName.startsWith("java.lang.Runtime");
  }

  private static boolean readsEnvironment(String ownerQName, String methodName) {
    if (ownerQName.endsWith("ClassLoader")) return true;
    if (!ownerQName.equals("java.lang.System")) return false;
    return switch (methodName) {
      case "getProperty", "getProperties", "getenv", "lineSeparator", "identityHashCode" -> true;
      default -> false;
    };
  }

  private static boolean isThreadConfined(String ownerQName) {
    return ownerQName.startsWith("java.lang.ThreadLocal")
        || ownerQName.startsWith("java.lang.InheritableThreadLocal");
  }

  private static boolean matchesAny(String qname, List<String> prefixes) {
    return prefixes.stream().anyMatch(qname::startsWith);
  }
}
