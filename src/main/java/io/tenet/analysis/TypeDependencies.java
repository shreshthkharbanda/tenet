package io.tenet.analysis;

import java.util.Set;

public record TypeDependencies(
        String sourceType,
        String sourcePackage,
        JavaSource source,
        Location location,
        Set<String> targetTypes) {
}

