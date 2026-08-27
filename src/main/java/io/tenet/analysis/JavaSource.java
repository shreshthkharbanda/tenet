package io.tenet.analysis;

import java.nio.file.Path;

public record JavaSource(Path absolutePath, String displayPath, String content) {
}

