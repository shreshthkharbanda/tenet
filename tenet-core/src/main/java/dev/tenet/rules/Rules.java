package dev.tenet.rules;

import dev.tenet.engine.TenetConfig;
import dev.tenet.rules.design.ConcreteReachDownRule;
import dev.tenet.rules.design.PatternCosplayRule;
import dev.tenet.rules.design.RefusedBequestRule;
import dev.tenet.rules.design.RoommateTypesRule;
import dev.tenet.rules.design.ScatteredDispatchRule;
import dev.tenet.rules.design.SplitBrainClassRule;
import dev.tenet.rules.effects.DiscardedFutureRule;
import dev.tenet.rules.effects.EffectLeakRule;
import dev.tenet.rules.effects.SwallowedFailureRule;
import dev.tenet.rules.fault.CheckThenActRule;
import dev.tenet.rules.fault.CompoundingRetriesRule;
import dev.tenet.rules.fault.RetriedNonIdempotentRule;
import dev.tenet.rules.fault.RetryWithoutPolicyRule;
import dev.tenet.rules.fault.SequentialIndependentCallsRule;
import dev.tenet.rules.fault.UnboundedFanOutRule;
import dev.tenet.rules.fault.UnboundedWaitRule;
import dev.tenet.rules.names.BooleanPredicateRule;
import dev.tenet.rules.names.LyingQueryRule;
import dev.tenet.rules.names.VagueIdentifierRule;
import dev.tenet.rules.names.VocabularyDriftRule;
import dev.tenet.rules.shape.BooleanFlagParameterRule;
import dev.tenet.rules.shape.CommandQueryRule;
import dev.tenet.rules.shape.GuardClauseRule;
import dev.tenet.rules.shape.ParameterSprawlRule;
import dev.tenet.rules.state.AmbientStaticStateRule;
import dev.tenet.rules.state.ParameterMutationRule;
import dev.tenet.rules.state.ReassignmentTheaterRule;
import dev.tenet.rules.truth.DuplicateLogicRule;
import dev.tenet.rules.truth.UnnamedConstantRule;
import dev.tenet.rules.types.BagOfNullablesRule;
import dev.tenet.rules.types.BooleanStateMachineRule;
import dev.tenet.rules.types.SilentNonExhaustiveRule;
import dev.tenet.rules.types.StringlyTypedRule;
import dev.tenet.rules.types.TypeLaunderingRule;
import java.util.List;

public final class Rules {

  private Rules() {}

  public static List<Rule> all() {
    return all(TenetConfig.defaults());
  }

  public static List<Rule> enabled(TenetConfig config) {
    return Profiles.enabled(config);
  }

  public static List<Rule> all(TenetConfig config) {
    return List.of(
        new LyingQueryRule(),
        new BooleanPredicateRule(),
        new VagueIdentifierRule(),
        new VocabularyDriftRule(),
        new BooleanFlagParameterRule(),
        new CommandQueryRule(),
        new GuardClauseRule(config),
        new ParameterSprawlRule(config),
        new AmbientStaticStateRule(),
        new ParameterMutationRule(),
        new ReassignmentTheaterRule(),
        new StringlyTypedRule(config),
        new BooleanStateMachineRule(),
        new BagOfNullablesRule(),
        new SilentNonExhaustiveRule(),
        new TypeLaunderingRule(),
        new SwallowedFailureRule(),
        new DiscardedFutureRule(),
        new EffectLeakRule(),
        new DuplicateLogicRule(),
        new UnnamedConstantRule(config),
        new SplitBrainClassRule(config),
        new ScatteredDispatchRule(config),
        new RefusedBequestRule(),
        new RoommateTypesRule(),
        new ConcreteReachDownRule(),
        new PatternCosplayRule(),
        new SequentialIndependentCallsRule(),
        new CheckThenActRule(),
        new UnboundedFanOutRule(),
        new RetryWithoutPolicyRule(),
        new CompoundingRetriesRule(),
        new RetriedNonIdempotentRule(),
        new UnboundedWaitRule());
  }
}
