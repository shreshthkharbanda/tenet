package com.acme.billing;

import com.acme.model.Policy;
import com.acme.model.Status;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PolicyService {

  private final Map<String, Policy> cache = new HashMap<>();
  private int hits;

    public Policy getPolicy(String id) throws Exception {
    hits = hits + 1;
    Files.writeString(Path.of("/tmp/policy-audit.log"), id, StandardCharsets.UTF_8);
    return cache.get(id);
  }

    public int tally(Policy policy) {
    hits = hits + 1;
    return hits;
  }

    public String render(boolean admin) {
    if (admin) {
      return "full-detail-view";
    } else {
      return "customer-view";
    }
  }

    public Policy createPolicy(String id, String owner, String region, Status status) {
    return new Policy(id, status);
  }

    public String describe(Policy policy, List<String> tags) {
    String label = "";
    if (policy != null) {
      if (policy.status() != null) {
        if (tags != null) {
          for (String tag : tags) {
            if (tag.length() > 3) {
              label = label + tag;
            }
          }
        } else {
          return "no-tags";
        }
      }
    }
    return label;
  }

    public String badge(Status status) {
    switch (status) {
      case PENDING:
        return "grey";
      case ACTIVE:
        return "green";
      default:
        return "unknown";
    }
  }

    public int settle(List<Integer> amounts) {
    int total = 0;
    for (Integer amount : amounts) {
      total = total + amount;
    }
    List<Integer> audit = new ArrayList<>(amounts);
    audit.add(total);
    return total;
  }

  public String mediaType() {
    return "application/vnd.acme+json";
  }
}
