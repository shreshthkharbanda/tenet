package com.acme.state;

public final class TrackerCaller {

  private final OrderTracker tracker = new OrderTracker();

  public void begin() {
    tracker.transition("LOADING", 1);
  }

  public void fail() {
    tracker.transition("FAILED", 2);
  }

  public void finish() {
    tracker.transition("COMPLETE", 3);
  }
}
