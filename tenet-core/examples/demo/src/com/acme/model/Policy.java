package com.acme.model;

public final class Policy {
  private final String id;
  private final Status status;

  public Policy(String id, Status status) {
    this.id = id;
    this.status = status;
  }

  public String id() {
    return id;
  }

  public Status status() {
    return status;
  }
}
