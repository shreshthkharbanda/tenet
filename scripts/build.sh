#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIRECTORY="$PROJECT_ROOT/build"
SOURCE_LIST="$BUILD_DIRECTORY/main-sources.txt"

rm -rf "$BUILD_DIRECTORY"
mkdir -p "$BUILD_DIRECTORY/classes"
find "$PROJECT_ROOT/src/main/java" -name '*.java' -type f -print | LC_ALL=C sort > "$SOURCE_LIST"

if command -v javac >/dev/null 2>&1; then
    JAVAC=(javac)
else
    JAVAC=(java -m jdk.compiler/com.sun.tools.javac.Main)
fi

if command -v jar >/dev/null 2>&1; then
    JAR=(jar)
else
    JAR=(java -m jdk.jartool/sun.tools.jar.Main)
fi

"${JAVAC[@]}" --release 17 -encoding UTF-8 -d "$BUILD_DIRECTORY/classes" "@$SOURCE_LIST"
"${JAR[@]}" --create --file "$BUILD_DIRECTORY/tenet.jar" --main-class io.tenet.cli.TenetMain -C "$BUILD_DIRECTORY/classes" .

