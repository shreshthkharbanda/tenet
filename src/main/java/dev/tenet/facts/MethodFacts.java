package dev.tenet.facts;

import dev.tenet.facts.patterns.BooleanFlagBranch;
import dev.tenet.facts.patterns.CatchFact;
import dev.tenet.facts.patterns.CheckThenAct;
import dev.tenet.facts.patterns.ConstExpressibleLocal;
import dev.tenet.facts.patterns.DiscardedFuture;
import dev.tenet.facts.patterns.IndependentBlockingPair;
import dev.tenet.facts.patterns.UnboundedWait;
import dev.tenet.facts.patterns.UncheckedUse;
import dev.tenet.model.SourceRef;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

public final class MethodFacts {

  private final MethodId id;
  private final SourceRef site;
  private final Visibility visibility;
  private final TypeName returnType;
  private final List<Param> params;
  private final boolean constructor;
  private final boolean staticMethod;
  private final boolean synchronizedMethod;
  private final boolean overrideAnnotated;
  private final boolean returnsValue;
  private final boolean returnsThis;
  private final boolean trivialAccessor;
  private final boolean throwsUnsupportedOnly;
  private final int statementCount;
  private final int maxNestingDepth;
  private final Optional<SourceRef> invertibleGuard;
  private final Optional<String> bodyHash;
  private final List<DirectEffect> effects;
  private final List<MethodId> callees;
  private final List<ExternalCall> externalCalls;
  private final List<FieldWrite> staticWrites;
  private final Set<String> ownFieldsAccessed;
  private final Set<String> ownBooleanFieldsSetTrue;
  private final Set<String> fieldsAssignedInConstructor;
  private final List<CatchFact> catches;
  private final List<DiscardedFuture> discardedFutures;
  private final List<IndependentBlockingPair> independentBlockingPairs;
  private final List<UnboundedWait> unboundedWaits;
  private final List<CheckThenAct> checkThenActs;
  private final List<BooleanFlagBranch> booleanFlagBranches;
  private final List<UncheckedUse> uncheckedUses;
  private final List<ConstExpressibleLocal> constExpressibleLocals;
  private final List<RetryScope> retryScopes;

  private MethodFacts(Builder b) {
    this.id = Objects.requireNonNull(b.id, "id");
    this.site = Objects.requireNonNull(b.site, "site");
    this.visibility = Objects.requireNonNull(b.visibility, "visibility");
    this.returnType = Objects.requireNonNull(b.returnType, "returnType");
    this.params = List.copyOf(b.params);
    this.constructor = b.constructor;
    this.staticMethod = b.staticMethod;
    this.synchronizedMethod = b.synchronizedMethod;
    this.overrideAnnotated = b.overrideAnnotated;
    this.returnsValue = b.returnsValue;
    this.returnsThis = b.returnsThis;
    this.trivialAccessor = b.trivialAccessor;
    this.throwsUnsupportedOnly = b.throwsUnsupportedOnly;
    this.statementCount = b.statementCount;
    this.maxNestingDepth = b.maxNestingDepth;
    this.invertibleGuard = Optional.ofNullable(b.invertibleGuard);
    this.bodyHash = Optional.ofNullable(b.bodyHash);
    this.effects = List.copyOf(b.effects);
    this.callees = List.copyOf(b.callees);
    this.externalCalls = List.copyOf(b.externalCalls);
    this.staticWrites = List.copyOf(b.staticWrites);
    this.ownFieldsAccessed = Set.copyOf(b.ownFieldsAccessed);
    this.ownBooleanFieldsSetTrue = Set.copyOf(b.ownBooleanFieldsSetTrue);
    this.fieldsAssignedInConstructor = Set.copyOf(b.fieldsAssignedInConstructor);
    this.catches = List.copyOf(b.catches);
    this.discardedFutures = List.copyOf(b.discardedFutures);
    this.independentBlockingPairs = List.copyOf(b.independentBlockingPairs);
    this.unboundedWaits = List.copyOf(b.unboundedWaits);
    this.checkThenActs = List.copyOf(b.checkThenActs);
    this.booleanFlagBranches = List.copyOf(b.booleanFlagBranches);
    this.uncheckedUses = List.copyOf(b.uncheckedUses);
    this.constExpressibleLocals = List.copyOf(b.constExpressibleLocals);
    this.retryScopes = List.copyOf(b.retryScopes);
  }

  public MethodId id() {
    return id;
  }

  public SourceRef site() {
    return site;
  }

  public Visibility visibility() {
    return visibility;
  }

  public TypeName returnType() {
    return returnType;
  }

  public List<Param> params() {
    return params;
  }

  public boolean isConstructor() {
    return constructor;
  }

  public boolean isStatic() {
    return staticMethod;
  }

  public boolean isSynchronized() {
    return synchronizedMethod;
  }

  public boolean isOverrideAnnotated() {
    return overrideAnnotated;
  }

  public boolean returnsValue() {
    return returnsValue;
  }

  public boolean returnsThis() {
    return returnsThis;
  }

  public boolean isTrivialAccessor() {
    return trivialAccessor;
  }

  public boolean throwsUnsupportedOnly() {
    return throwsUnsupportedOnly;
  }

  public int statementCount() {
    return statementCount;
  }

  public int maxNestingDepth() {
    return maxNestingDepth;
  }

  public Optional<SourceRef> invertibleGuard() {
    return invertibleGuard;
  }

  public Optional<String> bodyHash() {
    return bodyHash;
  }

  public List<DirectEffect> effects() {
    return effects;
  }

  public List<MethodId> callees() {
    return callees;
  }

  public List<ExternalCall> externalCalls() {
    return externalCalls;
  }

  public List<FieldWrite> staticWrites() {
    return staticWrites;
  }

  public Set<String> ownFieldsAccessed() {
    return ownFieldsAccessed;
  }

  public Set<String> ownBooleanFieldsSetTrue() {
    return ownBooleanFieldsSetTrue;
  }

  public Set<String> fieldsAssignedInConstructor() {
    return fieldsAssignedInConstructor;
  }

  public List<CatchFact> catches() {
    return catches;
  }

  public List<DiscardedFuture> discardedFutures() {
    return discardedFutures;
  }

  public List<IndependentBlockingPair> independentBlockingPairs() {
    return independentBlockingPairs;
  }

  public List<UnboundedWait> unboundedWaits() {
    return unboundedWaits;
  }

  public List<CheckThenAct> checkThenActs() {
    return checkThenActs;
  }

  public List<BooleanFlagBranch> booleanFlagBranches() {
    return booleanFlagBranches;
  }

  public List<UncheckedUse> uncheckedUses() {
    return uncheckedUses;
  }

  public List<ConstExpressibleLocal> constExpressibleLocals() {
    return constExpressibleLocals;
  }

  public List<RetryScope> retryScopes() {
    return retryScopes;
  }

  public String name() {
    return id.name();
  }

  public Optional<DirectEffect> firstProvenEffect() {
    return effects.stream().filter(DirectEffect::proven).findFirst();
  }

  public Optional<DirectEffect> firstEscapingEffect() {
    return effects.stream().filter(DirectEffect::escapesReceiver).findFirst();
  }

  public Optional<DirectEffect> firstSelfStateWrite() {
    return effects.stream()
        .filter(e -> e.kind() == DirectEffect.Kind.WRITE_INSTANCE)
        .findFirst();
  }

  public boolean hasUnknownExternal() {
    return effects.stream().anyMatch(e -> e.kind() == DirectEffect.Kind.UNKNOWN_EXTERNAL);
  }

  public String display() {
    return id.display() + " (" + site + ")";
  }

  public static Builder builder(MethodId id, SourceRef site) {
    return new Builder(id, site);
  }

  public static final class Builder {
    private final MethodId id;
    private final SourceRef site;
    private Visibility visibility = Visibility.PACKAGE_PRIVATE;
    private TypeName returnType = new TypeName("void");
    private final List<Param> params = new java.util.ArrayList<>();
    private boolean constructor;
    private boolean staticMethod;
    private boolean synchronizedMethod;
    private boolean overrideAnnotated;
    private boolean returnsValue;
    private boolean returnsThis;
    private boolean trivialAccessor;
    private boolean throwsUnsupportedOnly;
    private int statementCount;
    private int maxNestingDepth;
    private SourceRef invertibleGuard;
    private String bodyHash;
    private final List<DirectEffect> effects = new java.util.ArrayList<>();
    private final List<MethodId> callees = new java.util.ArrayList<>();
    private final List<ExternalCall> externalCalls = new java.util.ArrayList<>();
    private final List<FieldWrite> staticWrites = new java.util.ArrayList<>();
    private final Set<String> ownFieldsAccessed = new java.util.LinkedHashSet<>();
    private final Set<String> ownBooleanFieldsSetTrue = new java.util.LinkedHashSet<>();
    private final Set<String> fieldsAssignedInConstructor = new java.util.LinkedHashSet<>();
    private final List<CatchFact> catches = new java.util.ArrayList<>();
    private final List<DiscardedFuture> discardedFutures = new java.util.ArrayList<>();
    private final List<IndependentBlockingPair> independentBlockingPairs =
        new java.util.ArrayList<>();
    private final List<UnboundedWait> unboundedWaits = new java.util.ArrayList<>();
    private final List<CheckThenAct> checkThenActs = new java.util.ArrayList<>();
    private final List<BooleanFlagBranch> booleanFlagBranches = new java.util.ArrayList<>();
    private final List<UncheckedUse> uncheckedUses = new java.util.ArrayList<>();
    private final List<ConstExpressibleLocal> constExpressibleLocals = new java.util.ArrayList<>();
    private final List<RetryScope> retryScopes = new java.util.ArrayList<>();

    private Builder(MethodId id, SourceRef site) {
      this.id = id;
      this.site = site;
    }

    public Builder visibility(Visibility v) {
      this.visibility = v;
      return this;
    }

    public Builder returnType(TypeName t) {
      this.returnType = t;
      return this;
    }

    public Builder addParam(Param p) {
      this.params.add(p);
      return this;
    }

    public Builder constructor(boolean v) {
      this.constructor = v;
      return this;
    }

    public Builder staticMethod(boolean v) {
      this.staticMethod = v;
      return this;
    }

    public Builder synchronizedMethod(boolean v) {
      this.synchronizedMethod = v;
      return this;
    }

    public Builder overrideAnnotated(boolean v) {
      this.overrideAnnotated = v;
      return this;
    }

    public Builder returnsValue(boolean v) {
      this.returnsValue = v;
      return this;
    }

    public Builder returnsThis(boolean v) {
      this.returnsThis = v;
      return this;
    }

    public Builder trivialAccessor(boolean v) {
      this.trivialAccessor = v;
      return this;
    }

    public Builder throwsUnsupportedOnly(boolean v) {
      this.throwsUnsupportedOnly = v;
      return this;
    }

    public Builder statementCount(int v) {
      this.statementCount = v;
      return this;
    }

    public Builder maxNestingDepth(int v) {
      this.maxNestingDepth = v;
      return this;
    }

    public Builder invertibleGuard(SourceRef ref) {
      this.invertibleGuard = ref;
      return this;
    }

    public Builder bodyHash(String hash) {
      this.bodyHash = hash;
      return this;
    }

    public Builder addEffect(DirectEffect e) {
      this.effects.add(e);
      return this;
    }

    public Builder addCallee(MethodId m) {
      this.callees.add(m);
      return this;
    }

    public Builder addExternalCall(ExternalCall c) {
      this.externalCalls.add(c);
      return this;
    }

    public Builder addStaticWrite(FieldWrite w) {
      this.staticWrites.add(w);
      return this;
    }

    public Builder accessOwnField(String name) {
      this.ownFieldsAccessed.add(name);
      return this;
    }

    public Builder setOwnBooleanTrue(String name) {
      this.ownBooleanFieldsSetTrue.add(name);
      return this;
    }

    public Builder assignInConstructor(String name) {
      this.fieldsAssignedInConstructor.add(name);
      return this;
    }

    public Builder addCatch(CatchFact c) {
      this.catches.add(c);
      return this;
    }

    public Builder addDiscardedFuture(DiscardedFuture d) {
      this.discardedFutures.add(d);
      return this;
    }

    public Builder addIndependentPair(IndependentBlockingPair p) {
      this.independentBlockingPairs.add(p);
      return this;
    }

    public Builder addUnboundedWait(UnboundedWait w) {
      this.unboundedWaits.add(w);
      return this;
    }

    public Builder addCheckThenAct(CheckThenAct c) {
      this.checkThenActs.add(c);
      return this;
    }

    public Builder addBooleanFlagBranch(BooleanFlagBranch b) {
      this.booleanFlagBranches.add(b);
      return this;
    }

    public Builder addUncheckedUse(UncheckedUse u) {
      this.uncheckedUses.add(u);
      return this;
    }

    public Builder addConstExpressibleLocal(ConstExpressibleLocal c) {
      this.constExpressibleLocals.add(c);
      return this;
    }

    public Builder addRetryScope(RetryScope r) {
      this.retryScopes.add(r);
      return this;
    }

    public MethodFacts build() {
      return new MethodFacts(this);
    }
  }
}
