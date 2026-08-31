package dev.tenet.engine;

import dev.tenet.facts.ProgramFacts;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

public interface Frontend {

  ProgramFacts extract(List<Path> sourceRoots, List<Path> classpath) throws IOException;
}
