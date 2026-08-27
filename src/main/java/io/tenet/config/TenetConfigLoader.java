package io.tenet.config;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

public final class TenetConfigLoader {
    private TenetConfigLoader() {
    }

    public static TenetConfig load(final Path path) throws IOException {
        final Map<String, String> values = new LinkedHashMap<>(TenetConfig.defaultValues());
        if (path != null && Files.exists(path)) {
            loadProperties(path, values);
        }
        return new TenetConfig(values);
    }

    private static void loadProperties(final Path path, final Map<String, String> values) throws IOException {
        final Properties properties = new Properties();
        try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }
        properties.stringPropertyNames().stream()
                .sorted()
                .forEach(key -> values.put(key, properties.getProperty(key).trim()));
    }
}
