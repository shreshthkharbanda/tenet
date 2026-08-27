package io.tenet.analysis;

public record MethodFingerprint(
        String owner,
        String method,
        JavaSource source,
        Location location,
        String exactHash,
        String structuralHash,
        int bodyCharacters,
        int structuralNodes) {

    public String displayName() {
        return owner + "." + method;
    }
}

