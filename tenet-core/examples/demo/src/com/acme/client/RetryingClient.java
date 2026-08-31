package com.acme.client;

import com.acme.model.Policy;
import com.acme.model.Status;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class RetryingClient {

  private final Map<String, String> sessions = new HashMap<>();

    public Policy fetchPolicy(String id) {
    return new Policy(id, Status.ACTIVE);
  }

    public String callUntilItWorks(String path) {
    while (true) {
      try {
        return Files.readString(Path.of(path), StandardCharsets.UTF_8);
      } catch (Exception e) {
        try {
          Thread.sleep(100);
        } catch (InterruptedException ie) {
          Thread.currentThread().interrupt();
          throw new IllegalStateException(ie);
        }
      }
    }
  }

    public String resilientRead(String path) {
    for (int attempt = 0; attempt < 3; attempt++) {
      try {
        return callUntilItWorks(path);
      } catch (IllegalStateException e) {
        throw e;
      }
    }
    return "";
  }

    public String mergeConfigs() throws Exception {
    String primary = Files.readString(Path.of("/etc/acme/primary.conf"), StandardCharsets.UTF_8);
    String fallback = Files.readString(Path.of("/etc/acme/fallback.conf"), StandardCharsets.UTF_8);
    return primary + fallback;
  }

    public void openSession(String user, String token) {
    if (!sessions.containsKey(user)) {
      sessions.put(user, token);
    }
  }

    public void warmCaches() {
    ExecutorService pool = Executors.newCachedThreadPool();
    CompletableFuture.runAsync(() -> sessions.clear(), pool);
  }

    public String awaitResult(Future<String> pending) throws Exception {
    return pending.get();
  }

    public int priority(Status status) {
    switch (status) {
      case ACTIVE:
        return 1;
      case PENDING:
        return 2;
      default:
        return 9;
    }
  }
}
