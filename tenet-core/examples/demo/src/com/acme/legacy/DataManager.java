package com.acme.legacy;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DataManager {

  static Map<String, String> temp = new HashMap<>();
  static int flag;

  @SuppressWarnings("tenet:TNT-C01")
  public void process(String key, String value) {
    temp.put(key, value);
    flag = flag + 1;
  }

    public List<String> normalize(List<String> entries) {
    entries.add("normalized");
    return entries;
  }

    @SuppressWarnings("unchecked")
  public List copyAll(List source) {
    List target = new ArrayList();
    target.addAll(source);
    return target;
  }

    public void pause(long millis) {
    try {
      Thread.sleep(millis);
    } catch (InterruptedException e) {
      System.out.println("interrupted: " + e.getMessage());
    }
  }

    public String load(String path) {
    flag = flag + 1;
    try {
      return java.nio.file.Files.readString(java.nio.file.Path.of(path));
    } catch (Exception e) {
      System.err.println("load failed");
      return null;
    }
  }

  public String mimeType() {
    return "application/vnd.acme+json";
  }
}
