package dev.tenet;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import dev.tenet.engine.TenetConfig;
import dev.tenet.rules.Profiles;
import dev.tenet.rules.Rule;
import java.util.List;
import java.util.Properties;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ProfilesTest {

  private Set<String> idsFor(Properties properties) {
    List<Rule> rules = Profiles.enabled(TenetConfig.fromProperties(properties));
    return Set.copyOf(rules.stream().map(rule -> rule.descriptor().id()).toList());
  }

  @Test
  void consensusProfileExcludesDoctrineRules() {
    Set<String> ids = idsFor(new Properties());
    assertTrue(ids.contains("TNT-A01"));
    assertFalse(ids.contains("TNT-CC01"));
    assertFalse(ids.contains("TNT-DM01"));
  }

  @Test
  void cleanCodeProfileAddsItsSchoolOnly() {
    Properties properties = new Properties();
    properties.setProperty("profile", "clean-code");
    Set<String> ids = idsFor(properties);
    assertTrue(ids.contains("TNT-CC01"));
    assertTrue(ids.contains("TNT-CC02"));
    assertFalse(ids.contains("TNT-DM01"));
  }

  @Test
  void deepModulesProfileAddsItsSchoolOnly() {
    Properties properties = new Properties();
    properties.setProperty("profile", "deep-modules");
    Set<String> ids = idsFor(properties);
    assertTrue(ids.contains("TNT-DM01"));
    assertTrue(ids.contains("TNT-DM02"));
    assertFalse(ids.contains("TNT-CC01"));
  }

  @Test
  void opposingDoctrinesCannotBothBeEnabled() {
    Properties properties = new Properties();
    properties.setProperty("profile", "clean-code");
    properties.setProperty("rules.TNT-DM01.enabled", "true");
    assertThrows(IllegalArgumentException.class, () -> idsFor(properties));
  }

  @Test
  void singleDoctrineRuleCanBeOptedIntoConsensus() {
    Properties properties = new Properties();
    properties.setProperty("rules.TNT-DM01.enabled", "true");
    Set<String> ids = idsFor(properties);
    assertTrue(ids.contains("TNT-DM01"));
    assertFalse(ids.contains("TNT-DM02"));
  }

  @Test
  void profileRuleCanBeIndividuallyDisabled() {
    Properties properties = new Properties();
    properties.setProperty("profile", "clean-code");
    properties.setProperty("rules.TNT-CC02.enabled", "false");
    Set<String> ids = idsFor(properties);
    assertTrue(ids.contains("TNT-CC01"));
    assertFalse(ids.contains("TNT-CC02"));
  }

  @Test
  void conventionsAndDefensiveRulesLeftConsensus() {
    Set<String> ids = idsFor(new Properties());
    assertFalse(ids.contains("TNT-A02"));
    assertFalse(ids.contains("TNT-A03"));
    assertFalse(ids.contains("TNT-A04"));
    assertFalse(ids.contains("TNT-H03"));
    assertFalse(ids.contains("TNT-H06"));
  }

  @Test
  void conventionsProfileAddsNamingRules() {
    Properties properties = new Properties();
    properties.setProperty("profile", "conventions");
    Set<String> ids = idsFor(properties);
    assertTrue(ids.contains("TNT-A02"));
    assertTrue(ids.contains("TNT-A03"));
    assertTrue(ids.contains("TNT-A04"));
    assertFalse(ids.contains("TNT-H03"));
  }

  @Test
  void profilesCombineWithConflictChecking() {
    Properties properties = new Properties();
    properties.setProperty("profile", "conventions,defensive,clean-code");
    Set<String> ids = idsFor(properties);
    assertTrue(ids.contains("TNT-A03"));
    assertTrue(ids.contains("TNT-H06"));
    assertTrue(ids.contains("TNT-CC01"));
    assertFalse(ids.contains("TNT-DM01"));
  }

  @Test
  void unknownProfileFailsLoudly() {
    Properties properties = new Properties();
    properties.setProperty("profile", "grug-brained");
    assertThrows(IllegalArgumentException.class, () -> idsFor(properties));
  }
}
