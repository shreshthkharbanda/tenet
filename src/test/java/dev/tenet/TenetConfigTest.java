package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import dev.tenet.engine.TenetConfig;
import dev.tenet.rules.Rule;
import dev.tenet.rules.Rules;
import java.util.List;
import java.util.Properties;
import java.util.Set;
import org.junit.jupiter.api.Test;

class TenetConfigTest {

  @Test
  void defaultsEnableEveryRule() {
    TenetConfig config = TenetConfig.defaults();
    for (Rule rule : Rules.all()) {
      assertTrue(config.enabled(rule.descriptor().id()));
    }
  }

  @Test
  void propertiesDisableARule() {
    Properties properties = new Properties();
    properties.setProperty("rules.TNT-A03.enabled", "false");
    TenetConfig config = TenetConfig.fromProperties(properties);

    assertFalse(config.enabled("TNT-A03"));
    assertTrue(config.enabled("TNT-A01"));
    List<Rule> enabled = Rules.enabled(config);
    assertTrue(enabled.stream().noneMatch(rule -> rule.descriptor().id().equals("TNT-A03")));
  }

  @Test
  void propertiesOverrideAThreshold() {
    Properties properties = new Properties();
    properties.setProperty("rules.TNT-B04.maxParams", "9");
    TenetConfig config = TenetConfig.fromProperties(properties);

    assertEquals(9, config.intParam("TNT-B04", "maxParams", 4));
    Rule sprawl =
        Rules.all(config).stream()
            .filter(rule -> rule.descriptor().id().equals("TNT-B04"))
            .findFirst()
            .orElseThrow();
    assertTrue(sprawl.descriptor().mechanism().contains("More than 9"));
  }

  @Test
  void onlyOverlayWinsOverEverything() {
    Properties properties = new Properties();
    properties.setProperty("rules.TNT-A01.enabled", "false");
    TenetConfig config = TenetConfig.fromProperties(properties).withOnly(Set.of("TNT-A01"));

    assertTrue(config.enabled("TNT-A01"));
    assertFalse(config.enabled("TNT-B01"));
  }

  @Test
  void disableOverlayStacksWithProperties() {
    Properties properties = new Properties();
    properties.setProperty("rules.TNT-A03.enabled", "false");
    TenetConfig config = TenetConfig.fromProperties(properties).withDisabled(Set.of("TNT-F02"));

    assertFalse(config.enabled("TNT-A03"));
    assertFalse(config.enabled("TNT-F02"));
    assertTrue(config.enabled("TNT-A01"));
  }
}
