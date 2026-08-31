package com.acme.billing;

import java.util.ArrayList;
import java.util.List;

public final class LedgerService {

    public int settle(List<Integer> amounts) {
    int total = 0;
    for (Integer amount : amounts) {
      total = total + amount;
    }
    List<Integer> audit = new ArrayList<>(amounts);
    audit.add(total);
    return total;
  }

  public String contentType() {
    return "application/vnd.acme+json";
  }
}
