package com.acme.state;

import com.acme.model.Status;

public final class OrderTracker {

  private boolean isLoading;
  private boolean isFailed;
  private boolean isComplete;
  private String lastError;
  private long updatedAt;

  public void markLoading() {
    isLoading = true;
    isFailed = false;
    isComplete = false;
  }

  public void markFailed(String error) {
    isLoading = false;
    isFailed = true;
    isComplete = false;
    lastError = error;
  }

  public void markComplete(long at) {
    isLoading = false;
    isFailed = false;
    isComplete = true;
    updatedAt = at;
  }

    public void transition(String phase, int attempt) {
    if (phase.equals("LOADING")) markLoading();
    if (phase.equals("FAILED")) markFailed("attempt " + attempt);
    if (phase.equals("COMPLETE")) markComplete(attempt);
  }

    public boolean terminal(Status status) {
    switch (status) {
      case CLOSED:
        return true;
      case SUSPENDED:
        return true;
      default:
        return false;
    }
  }

  public String describeState() {
    if (isComplete) return "complete at " + updatedAt;
    if (isFailed) return "failed: " + lastError;
    return isLoading ? "loading" : "idle";
  }
}
