package com.acme.client;

public final class ClientFactory {

  public RetryingClient createClient() {
    return new RetryingClient();
  }

  public RetryingClient createSecureClient() {
    return new RetryingClient();
  }
}
