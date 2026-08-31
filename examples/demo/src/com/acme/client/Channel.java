package com.acme.client;

public class Channel {

  public void send(String message) {
    System.out.println(message);
  }

  public String receive() {
    return "ok";
  }
}
