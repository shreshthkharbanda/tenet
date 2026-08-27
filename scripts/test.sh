#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIRECTORY="$PROJECT_ROOT/build"
SOURCE_LIST="$BUILD_DIRECTORY/test-sources.txt"

"$PROJECT_ROOT/scripts/build.sh"
mkdir -p "$BUILD_DIRECTORY/test-classes"
find "$PROJECT_ROOT/src/test/java" -name '*.java' -type f -print | LC_ALL=C sort > "$SOURCE_LIST"

if command -v javac >/dev/null 2>&1; then
    JAVAC=(javac)
else
    JAVAC=(java -m jdk.compiler/com.sun.tools.javac.Main)
fi

"${JAVAC[@]}" --release 17 -encoding UTF-8 -cp "$BUILD_DIRECTORY/classes" -d "$BUILD_DIRECTORY/test-classes" "@$SOURCE_LIST"
java -cp "$BUILD_DIRECTORY/classes:$BUILD_DIRECTORY/test-classes" io.tenet.tests.TestRunner

