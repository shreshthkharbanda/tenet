package com.acme.client;

public class ReadOnlyChannel extends Channel {

  @Override
  public void send(String message) {
    throw new UnsupportedOperationException("read-only channel");
  }
}
