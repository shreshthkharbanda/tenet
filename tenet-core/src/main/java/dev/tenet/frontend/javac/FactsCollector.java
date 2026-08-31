package dev.tenet.frontend.javac;

import com.sun.source.tree.AnnotationTree;
import com.sun.source.tree.AssignmentTree;
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.CompoundAssignmentTree;
import com.sun.source.tree.ExpressionStatementTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.LiteralTree;
import com.sun.source.tree.MemberSelectTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.ModifiersTree;
import com.sun.source.tree.NewClassTree;
import com.sun.source.tree.ParameterizedTypeTree;
import com.sun.source.tree.SwitchExpressionTree;
import com.sun.source.tree.SwitchTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.UnaryTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;
import dev.tenet.facts.CallSite;
import dev.tenet.facts.ClassFacts;
import dev.tenet.facts.DirectEffect;
import dev.tenet.facts.ExternalCall;
import dev.tenet.facts.FieldFacts;
import dev.tenet.facts.FieldId;
import dev.tenet.facts.FieldWrite;
import dev.tenet.facts.MethodFacts;
import dev.tenet.facts.MethodId;
import dev.tenet.facts.Param;
import dev.tenet.facts.ProgramFacts;
import dev.tenet.facts.RetryScope;
import dev.tenet.facts.SuppressionScope;
import dev.tenet.facts.TypeName;
import dev.tenet.facts.Visibility;
import dev.tenet.facts.patterns.BooleanFlagBranch;
import dev.tenet.facts.patterns.CatchFact;
import dev.tenet.facts.patterns.CheckThenAct;
import dev.tenet.facts.patterns.ConstExpressibleLocal;
import dev.tenet.facts.patterns.DiscardedFuture;
import dev.tenet.facts.patterns.IndependentBlockingPair;
import dev.tenet.facts.patterns.UnboundedWait;
import dev.tenet.facts.patterns.UncheckedUse;
import dev.tenet.model.SourceRef;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.NestingKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;

final class FactsCollector extends TreePathScanner<Void, Void> {

  private static final Set<String> MUTATOR_NAMES =
      Set.of(
          "add",
          "addAll",
          "put",
          "putAll",
          "remove",
          "removeAll",
          "retainAll",
          "removeIf",
          "clear",
          "set",
          "push",
          "pop",
          "poll",
          "offer",
          "sort",
          "replaceAll",
          "merge");

  private static final Set<String> MUTABLE_COLLECTION_TYPES =
      Set.of(
          "java.util.List",
          "java.util.Map",
          "java.util.Set",
          "java.util.Collection",
          "java.util.Queue",
          "java.util.Deque",
          "java.util.ArrayList",
          "java.util.LinkedList",
          "java.util.HashMap",
          "java.util.HashSet",
          "java.util.TreeMap",
          "java.util.TreeSet",
          "java.util.LinkedHashMap",
          "java.util.LinkedHashSet",
          "java.util.ArrayDeque",
          "java.util.PriorityQueue",
          "java.lang.StringBuilder",
          "java.util.concurrent.ConcurrentHashMap",
          "java.util.concurrent.ConcurrentMap",
          "java.util.concurrent.CopyOnWriteArrayList");

  private final Trees trees;
  private final Ids ids;
  private final Set<String> repoTypeNames;
  private final ProgramFacts.Builder program;
  private final SourcePositions positions;

  private CompilationUnitTree unit;
  private String fileName;
  private final Deque<ClassContext> classStack = new ArrayDeque<>();
  private final Deque<MethodContext> methodStack = new ArrayDeque<>();
  private int annotationDepth;

  FactsCollector(Trees trees, Ids ids, Set<String> repoTypeNames, ProgramFacts.Builder program) {
    this.trees = trees;
    this.ids = ids;
    this.repoTypeNames = repoTypeNames;
    this.program = program;
    this.positions = trees.getSourcePositions();
  }

  void collect(CompilationUnitTree compilationUnit) {
    this.unit = compilationUnit;
    this.fileName = compilationUnit.getSourceFile().getName();
    scan(compilationUnit, null);
  }

  @Override
  public Void visitClass(ClassTree tree, Void unused) {
    Element element = trees.getElement(getCurrentPath());
    if (!(element instanceof TypeElement type) || isLocalOrAnonymous(type)) return null;
    ClassContext context =
        new ClassContext(
            type,
            ClassFacts.builder(ids.typeName(type), refOf(tree))
                .kind(kindOf(tree))
                .visibility(visibilityOf(type.getModifiers()))
                .nested(type.getNestingKind() != NestingKind.TOP_LEVEL)
                .abstractType(type.getModifiers().contains(Modifier.ABSTRACT)));
    recordSupertypes(type, context.builder);
    recordEnumConstants(type, context.builder);
    recordTenetSuppressions(type.getAnnotation(SuppressWarnings.class), tree);
    classStack.push(context);
    super.visitClass(tree, unused);
    classStack.pop();
    program.addClass(context.builder.build());
    return null;
  }

  private boolean isLocalOrAnonymous(TypeElement type) {
    NestingKind nesting = type.getNestingKind();
    return nesting == NestingKind.LOCAL || nesting == NestingKind.ANONYMOUS;
  }

  private ClassFacts.Kind kindOf(ClassTree tree) {
    return switch (tree.getKind()) {
      case INTERFACE -> ClassFacts.Kind.INTERFACE;
      case ENUM -> ClassFacts.Kind.ENUM;
      case RECORD -> ClassFacts.Kind.RECORD;
      case ANNOTATION_TYPE -> ClassFacts.Kind.ANNOTATION;
      default -> ClassFacts.Kind.CLASS;
    };
  }

  private void recordSupertypes(TypeElement type, ClassFacts.Builder builder) {
    TypeMirror superclass = type.getSuperclass();
    if (superclass.getKind() == TypeKind.DECLARED) {
      String qname = ids.erasedQName(superclass);
      if (!qname.equals("java.lang.Object")) builder.superType(new TypeName(qname));
    }
    for (TypeMirror implemented : type.getInterfaces()) {
      builder.addInterface(new TypeName(ids.erasedQName(implemented)));
    }
  }

  private void recordEnumConstants(TypeElement type, ClassFacts.Builder builder) {
    for (Element enclosed : type.getEnclosedElements()) {
      if (enclosed.getKind() == ElementKind.ENUM_CONSTANT) {
        builder.addEnumConstant(enclosed.getSimpleName().toString());
      }
    }
  }

  @Override
  public Void visitMethod(MethodTree tree, Void unused) {
    ClassContext classContext = classStack.peek();
    Element element = trees.getElement(getCurrentPath());
    if (classContext == null || !(element instanceof ExecutableElement executable)) return null;

    recordTenetSuppressions(executable.getAnnotation(SuppressWarnings.class), tree);
    MethodContext context = openMethodContext(tree, executable, classContext);
    methodStack.push(context);
    super.visitMethod(tree, unused);
    methodStack.pop();
    finishMethod(tree, context, classContext);
    return null;
  }

  private MethodContext openMethodContext(
      MethodTree tree, ExecutableElement executable, ClassContext classContext) {
    MethodId id = ids.methodId(executable);
    boolean isCtor = executable.getKind() == ElementKind.CONSTRUCTOR;
    MethodFacts.Builder builder =
        MethodFacts.builder(id, refOf(tree))
            .visibility(visibilityOf(executable.getModifiers()))
            .constructor(isCtor)
            .staticMethod(executable.getModifiers().contains(Modifier.STATIC))
            .synchronizedMethod(executable.getModifiers().contains(Modifier.SYNCHRONIZED))
            .overrideAnnotated(hasAnnotation(tree.getModifiers(), "Override"));
    TypeMirror returnType = executable.getReturnType();
    String erasedReturn =
        returnType.getKind() == TypeKind.VOID ? "void" : ids.erasedQName(returnType);

    boolean returnsValue = !erasedReturn.equals("void") && !erasedReturn.equals("java.lang.Void");
    builder.returnsValue(returnsValue).returnType(new TypeName(erasedReturn));

    Set<String> booleanParams = new LinkedHashSet<>();
    for (VariableElement param : executable.getParameters()) {
      String erased = ids.erasedQName(param.asType());
      boolean isBoolean = isBooleanTypeName(erased);
      builder.addParam(
          new Param(param.getSimpleName().toString(), new TypeName(erased), isBoolean));
      if (isBoolean) booleanParams.add(param.getSimpleName().toString());
    }
    if (hasSuppressUnchecked(tree.getModifiers())) {
      builder.addUncheckedUse(
          new UncheckedUse(
              UncheckedUse.Kind.SUPPRESS_UNCHECKED,
              "@SuppressWarnings(\"unchecked\")",
              refOf(tree)));
    }
    if (isCtor) classContext.builder.addConstructor(id);
    else classContext.builder.addMethod(id);
    return new MethodContext(executable, id, builder, isCtor, booleanParams);
  }

  private void finishMethod(MethodTree tree, MethodContext context, ClassContext classContext) {
    BodySyntax.Shape shape = BodySyntax.shape(tree, this::lineOf);
    context
        .builder
        .statementCount(shape.statementCount())
        .maxNestingDepth(shape.maxNesting())
        .returnsThis(shape.returnsThis())
        .trivialAccessor(shape.trivialAccessor())
        .throwsUnsupportedOnly(shape.throwsUnsupportedOnly());
    if (shape.invertibleGuardLine() > 0) {
      context.builder.invertibleGuard(new SourceRef(fileName, shape.invertibleGuardLine()));
    }
    BodySyntax.bodyHash(tree).ifPresent(context.builder::bodyHash);
    BodySyntax.booleanFlagParam(tree, context.booleanParams)
        .ifPresent(
            param ->
                context.builder.addBooleanFlagBranch(new BooleanFlagBranch(param, refOf(tree))));
    for (BodySyntax.BranchAssignedLocal local :
        BodySyntax.branchAssignedLocals(tree, this::lineOf)) {
      context.builder.addConstExpressibleLocal(
          new ConstExpressibleLocal(local.name(), new SourceRef(fileName, local.line())));
    }
    for (BodySyntax.RawCatch caught : BodySyntax.catches(tree, this::lineOf)) {
      context.builder.addCatch(
          new CatchFact(
              caught.typeText(),
              disposalOf(caught.disposal()),
              caught.interrupted(),
              caught.reinterrupts(),
              caught.insideLoop(),
              new SourceRef(fileName, caught.line())));
    }
    for (BodySyntax.RawCheckAct race :
        BodySyntax.checkThenActs(tree, classContext.collectionFieldNames(), this::lineOf)) {
      context.builder.addCheckThenAct(
          new CheckThenAct(
              race.receiver(),
              race.checkCall(),
              race.actCall(),
              new SourceRef(fileName, race.line())));
    }
    recordRetryScopes(tree, context);
    recordIndependentPairs(tree, context);
    program.addMethod(context.builder.build());
  }

  private CatchFact.Disposal disposalOf(BodySyntax.Disposal disposal) {
    return switch (disposal) {
      case EMPTY -> CatchFact.Disposal.EMPTY;
      case LOG_ONLY -> CatchFact.Disposal.LOG_ONLY;
      case RETURNS_DEFAULT -> CatchFact.Disposal.RETURNS_DEFAULT;
      case RETHROWS -> CatchFact.Disposal.RETHROWS;
      case HANDLES -> CatchFact.Disposal.HANDLES;
    };
  }

  private void recordRetryScopes(MethodTree tree, MethodContext context) {
    for (BodySyntax.RawRetryLoop loop :
        BodySyntax.retryLoops(tree, this::lineOf, this::endLineOf)) {
      List<MethodId> inRepo = new ArrayList<>();
      List<ExternalCall> external = new ArrayList<>();
      for (RecordedCall call : context.calls) {
        if (call.line() < loop.tryStartLine() || call.line() > loop.tryEndLine()) continue;
        call.inRepo().ifPresent(inRepo::add);
        call.external().ifPresent(external::add);
      }
      if (inRepo.isEmpty() && external.isEmpty()) continue;
      context.builder.addRetryScope(
          new RetryScope(
              new SourceRef(fileName, loop.loopLine()),
              loop.bounded(),
              loop.classifiedErrors(),
              loop.hasSleep(),
              loop.sleepGrows(),
              inRepo,
              external));
    }
  }

  private void recordIndependentPairs(MethodTree tree, MethodContext context) {
    for (List<BodySyntax.InvocationDecl> pair :
        BodySyntax.consecutiveInvocationDecls(tree, this::lineOf)) {
      BodySyntax.InvocationDecl first = pair.get(0);
      BodySyntax.InvocationDecl second = pair.get(1);
      boolean bothBlocking =
          hasIoCallAt(context, first.line()) && hasIoCallAt(context, second.line());
      boolean independent = !second.identifiersUsed().contains(first.varName());
      if (bothBlocking && independent) {
        context.builder.addIndependentPair(
            new IndependentBlockingPair(
                first.callText(), new SourceRef(fileName, first.line()),
                second.callText(), new SourceRef(fileName, second.line())));
      }
    }
  }

  private boolean hasIoCallAt(MethodContext context, long line) {
    return context.calls.stream()
        .anyMatch(
            call ->
                call.line() == line
                    && call.external()
                        .map(e -> e.effectClass() == ExternalCall.EffectClass.IO)
                        .orElse(false));
  }

  @Override
  public Void visitVariable(VariableTree tree, Void unused) {
    TreePath parentPath = getCurrentPath().getParentPath();
    Tree parent = parentPath == null ? null : parentPath.getLeaf();
    if (parent instanceof ClassTree) {
      recordField(tree);
    } else if (parent instanceof MethodTree) {
      return super.visitVariable(tree, unused);
    } else {
      recordLocal(tree);
    }
    return super.visitVariable(tree, unused);
  }

  private void recordField(VariableTree tree) {
    ClassContext classContext = classStack.peek();
    Element element = trees.getElement(getCurrentPath());
    if (classContext == null || !(element instanceof VariableElement field)) return;
    if (field.getKind() != ElementKind.FIELD) return;
    String erased = ids.erasedQName(field.asType());
    FieldFacts facts =
        new FieldFacts(
            new FieldId(classContext.name(), field.getSimpleName().toString()),
            new TypeName(erased),
            refOf(tree),
            visibilityOf(field.getModifiers()),
            field.getModifiers().contains(Modifier.STATIC),
            field.getModifiers().contains(Modifier.FINAL),
            isBooleanTypeName(erased),
            MUTABLE_COLLECTION_TYPES.contains(erased),
            ExternalCallClassifier.isInfrastructureType(erased),
            tree.getInitializer() != null);
    classContext.builder.addField(facts);
    classContext.fieldsByName.put(facts.id().name(), facts);
  }

  private void recordLocal(VariableTree tree) {
    MethodContext context = methodStack.peek();
    if (context == null) return;
    if (tree.getInitializer() != null
        && BodySyntax.unwrap(tree.getInitializer()) instanceof NewClassTree) {
      context.newLocals.add(tree.getName().toString());
    }
    recordRawTypeUse(tree.getType(), context);
  }

  private void recordRawTypeUse(Tree typeTree, MethodContext context) {
    if (typeTree == null || typeTree instanceof ParameterizedTypeTree) return;
    TreePath typePath = TreePath.getPath(getCurrentPath(), typeTree);
    if (typePath == null) return;
    TypeMirror mirror = trees.getTypeMirror(typePath);
    if (mirror instanceof DeclaredType declared
        && declared.getTypeArguments().isEmpty()
        && declared.asElement() instanceof TypeElement type
        && !type.getTypeParameters().isEmpty()) {
      context.builder.addUncheckedUse(
          new UncheckedUse(
              UncheckedUse.Kind.RAW_TYPE, type.getSimpleName().toString(), refOf(typeTree)));
    }
  }

  @Override
  public Void visitMethodInvocation(MethodInvocationTree tree, Void unused) {
    MethodContext context = methodStack.peek();
    if (context != null) {
      recordInvocation(tree, context);
    }
    return super.visitMethodInvocation(tree, unused);
  }

  private void recordInvocation(MethodInvocationTree tree, MethodContext context) {
    Element element = trees.getElement(getCurrentPath());
    SourceRef site = refOf(tree);
    if (!(element instanceof ExecutableElement callee)) {
      context.builder.addEffect(
          new DirectEffect(
              DirectEffect.Kind.UNKNOWN_EXTERNAL,
              "unresolved " + BodySyntax.invokedName(tree),
              site));
      return;
    }
    TypeElement owner = Ids.enclosingType(callee);
    if (owner == null) return;
    String ownerQName = owner.getQualifiedName().toString();

    if (repoTypeNames.contains(ownerQName)) {
      MethodId calleeId = ids.methodId(callee);
      context.builder.addCallee(calleeId);
      context.calls.add(RecordedCall.inRepo(site.line(), calleeId));
      program.addCallSite(new CallSite(calleeId, context.id, argumentsOf(tree), site));
    } else {
      recordExternalCall(tree, callee, ownerQName, context, site);
    }
    recordMutatorOnReceiver(tree, context, site);
    recordAsyncHazards(tree, callee, ownerQName, context, site);
  }

  private void recordExternalCall(
      MethodInvocationTree tree,
      ExecutableElement callee,
      String ownerQName,
      MethodContext context,
      SourceRef site) {
    String methodName = callee.getSimpleName().toString();
    ExternalCall.EffectClass effectClass = ExternalCallClassifier.classify(ownerQName, methodName);
    ExternalCall call = new ExternalCall(new TypeName(ownerQName), methodName, effectClass, site);
    context.builder.addExternalCall(call);
    context.calls.add(RecordedCall.external(site.line(), call));
    switch (effectClass) {
      case IO -> context.builder.addEffect(
          new DirectEffect(DirectEffect.Kind.IO_CALL, call.display(), site));
      case LOGGING -> context.builder.addEffect(
          new DirectEffect(DirectEffect.Kind.LOG_CALL, call.display(), site));
      case UNKNOWN -> context.builder.addEffect(
          new DirectEffect(DirectEffect.Kind.UNKNOWN_EXTERNAL, call.display(), site));
      case PURE, LOCAL_MUTATION -> {}
    }
  }

  private void recordMutatorOnReceiver(
      MethodInvocationTree tree, MethodContext context, SourceRef site) {
    String mutator = BodySyntax.invokedName(tree);
    if (!MUTATOR_NAMES.contains(mutator)) return;
    if (!(tree.getMethodSelect() instanceof MemberSelectTree select)) return;
    TreePath basePath =
        TreePath.getPath(getCurrentPath(), BodySyntax.unwrap(select.getExpression()));
    if (basePath == null) return;
    Element base = trees.getElement(basePath);
    if (!(base instanceof VariableElement variable)) return;
    if (variable.getKind() == ElementKind.PARAMETER) {
      context.builder.addEffect(
          new DirectEffect(
              DirectEffect.Kind.PARAM_MUTATION,
              variable.getSimpleName() + " via ." + mutator + "(...)",
              site));
    } else {
      recordWriteTarget(variable, "mutator " + mutator, null, context, site);
    }
  }

  private void recordAsyncHazards(
      MethodInvocationTree tree,
      ExecutableElement callee,
      String ownerQName,
      MethodContext context,
      SourceRef site) {
    String name = callee.getSimpleName().toString();
    boolean concurrentOwner =
        Set.of(
                "java.util.concurrent.Future",
                "java.util.concurrent.CompletableFuture",
                "java.util.concurrent.CompletionStage",
                "java.util.concurrent.FutureTask",
                "java.util.concurrent.ForkJoinTask")
            .contains(ownerQName);
    if (concurrentOwner && name.equals("get") && tree.getArguments().isEmpty()) {
      context.builder.addUnboundedWait(
          new UnboundedWait(UnboundedWait.Kind.FUTURE_GET, callText(tree), site));
    } else if (concurrentOwner && name.equals("join") && tree.getArguments().isEmpty()) {
      context.builder.addUnboundedWait(
          new UnboundedWait(UnboundedWait.Kind.FUTURE_JOIN, callText(tree), site));
    }
    Tree parent = getCurrentPath().getParentPath().getLeaf();
    boolean discarded =
        parent instanceof ExpressionStatementTree
            && ids.erasedQName(callee.getReturnType()).contains("Future");
    if (discarded) {
      boolean handled =
          Set.of(
                  "whenComplete",
                  "whenCompleteAsync",
                  "exceptionally",
                  "exceptionallyAsync",
                  "handle",
                  "handleAsync")
              .contains(name);
      context.builder.addDiscardedFuture(new DiscardedFuture(callText(tree), handled, site));
    }
  }

  private List<CallSite.Argument> argumentsOf(MethodInvocationTree tree) {
    List<CallSite.Argument> arguments = new ArrayList<>();
    for (ExpressionTree arg : tree.getArguments()) {
      ExpressionTree unwrapped = BodySyntax.unwrap(arg);
      if (unwrapped instanceof LiteralTree literal && literal.getValue() != null) {
        arguments.add(CallSite.Argument.ofLiteral(String.valueOf(literal.getValue())));
      } else {
        arguments.add(CallSite.Argument.nonLiteral());
      }
    }
    return arguments;
  }

  private String callText(MethodInvocationTree tree) {
    return BodySyntax.displayCall(tree.getMethodSelect().toString());
  }

  private static boolean isBooleanTypeName(String erased) {
    return erased.equals("boolean") || erased.equals(Boolean.class.getName());
  }

  @Override
  public Void visitNewClass(NewClassTree tree, Void unused) {
    MethodContext context = methodStack.peek();
    Element element = trees.getElement(getCurrentPath());
    if (context != null && element instanceof ExecutableElement ctor) {
      TypeElement owner = Ids.enclosingType(ctor);
      String ownerQName = owner == null ? "" : owner.getQualifiedName().toString();
      SourceRef site = refOf(tree);
      if (repoTypeNames.contains(ownerQName)) {
        MethodId calleeId = ids.methodId(ctor);
        context.builder.addCallee(calleeId);
        context.calls.add(RecordedCall.inRepo(site.line(), calleeId));
        program.addCallSite(new CallSite(calleeId, context.id, List.of(), site));
      } else if (ExternalCallClassifier.isInfrastructureType(ownerQName)) {
        ExternalCall call =
            new ExternalCall(new TypeName(ownerQName), "<init>", ExternalCall.EffectClass.IO, site);
        context.builder.addExternalCall(call);
        context.builder.addEffect(
            new DirectEffect(DirectEffect.Kind.IO_CALL, call.display(), site));
      }
      recordRawConstruction(tree, ctor, context, site);
    }
    return super.visitNewClass(tree, unused);
  }

  private void recordRawConstruction(
      NewClassTree tree, ExecutableElement ctor, MethodContext context, SourceRef site) {
    boolean parameterized = tree.getIdentifier() instanceof ParameterizedTypeTree;
    TypeElement constructed = Ids.enclosingType(ctor);
    if (!parameterized && constructed != null && !constructed.getTypeParameters().isEmpty()) {
      context.builder.addUncheckedUse(
          new UncheckedUse(
              UncheckedUse.Kind.RAW_TYPE, constructed.getSimpleName().toString(), site));
    }
  }

  @Override
  public Void visitAssignment(AssignmentTree tree, Void unused) {
    recordWrite(tree.getVariable(), BodySyntax.unwrap(tree.getExpression()));
    return super.visitAssignment(tree, unused);
  }

  @Override
  public Void visitCompoundAssignment(CompoundAssignmentTree tree, Void unused) {
    recordWrite(tree.getVariable(), null);
    return super.visitCompoundAssignment(tree, unused);
  }

  @Override
  public Void visitUnary(UnaryTree tree, Void unused) {
    switch (tree.getKind()) {
      case PREFIX_INCREMENT, POSTFIX_INCREMENT, PREFIX_DECREMENT, POSTFIX_DECREMENT -> recordWrite(
          tree.getExpression(), null);
      default -> {}
    }
    return super.visitUnary(tree, unused);
  }

  private void recordWrite(ExpressionTree variable, ExpressionTree assignedValue) {
    MethodContext context = methodStack.peek();
    if (context == null) return;
    ExpressionTree target = BodySyntax.unwrap(variable);
    TreePath targetPath = TreePath.getPath(getCurrentPath(), target);
    if (targetPath == null) return;
    Element element = trees.getElement(targetPath);
    if (!(element instanceof VariableElement written)) return;
    SourceRef site = refOf(target);

    if (written.getKind() == ElementKind.FIELD) {
      recordWriteTarget(written, written.getSimpleName().toString(), assignedValue, context, site);
      recordReceiverMutation(target, context, site);
    }
  }

  private void recordWriteTarget(
      VariableElement written,
      String description,
      ExpressionTree assignedValue,
      MethodContext context,
      SourceRef site) {
    if (written.getKind() != ElementKind.FIELD) return;
    ClassContext classContext = classStack.peek();
    TypeElement owner = Ids.enclosingType(written);
    boolean ownField =
        classContext != null && owner != null && owner.equals(classContext.element());
    String fieldName = written.getSimpleName().toString();

    if (written.getModifiers().contains(Modifier.STATIC)) {
      if (owner != null) {
        FieldId fieldId = new FieldId(new TypeName(owner.getQualifiedName().toString()), fieldName);
        context.builder.addStaticWrite(new FieldWrite(fieldId, site));
      }
      context.builder.addEffect(
          new DirectEffect(DirectEffect.Kind.WRITE_STATIC, description, site));
      return;
    }
    if (ownField) {
      context.builder.accessOwnField(fieldName);
      if (isLiteralTrue(assignedValue)) context.builder.setOwnBooleanTrue(fieldName);
      if (context.isCtor) {
        context.builder.assignInConstructor(fieldName);
      } else {
        context.builder.addEffect(
            new DirectEffect(DirectEffect.Kind.WRITE_INSTANCE, description, site));
      }
    }
  }

  private void recordReceiverMutation(
      ExpressionTree target, MethodContext context, SourceRef site) {
    if (!(target instanceof MemberSelectTree select)) return;
    ExpressionTree base = BodySyntax.unwrap(select.getExpression());
    TreePath basePath = TreePath.getPath(getCurrentPath(), base);
    if (basePath == null) return;
    Element baseElement = trees.getElement(basePath);
    if (baseElement instanceof VariableElement variable
        && variable.getKind() == ElementKind.PARAMETER) {
      context.builder.addEffect(
          new DirectEffect(
              DirectEffect.Kind.PARAM_MUTATION, variable.getSimpleName().toString(), site));
    } else if (baseElement instanceof VariableElement variable
        && variable.getKind() == ElementKind.LOCAL_VARIABLE
        && !context.newLocals.contains(variable.getSimpleName().toString())) {
      context.builder.addEffect(
          new DirectEffect(
              DirectEffect.Kind.UNKNOWN_EXTERNAL,
              "write through alias " + variable.getSimpleName(),
              site));
    }
  }

  private boolean isLiteralTrue(ExpressionTree expression) {
    return expression instanceof LiteralTree literal && Boolean.TRUE.equals(literal.getValue());
  }

  @Override
  public Void visitIdentifier(IdentifierTree tree, Void unused) {
    MethodContext context = methodStack.peek();
    ClassContext classContext = classStack.peek();
    if (context != null && classContext != null) {
      Element element = trees.getElement(getCurrentPath());
      boolean ownInstanceField =
          element instanceof VariableElement variable
              && variable.getKind() == ElementKind.FIELD
              && !variable.getModifiers().contains(Modifier.STATIC)
              && classContext.element().equals(Ids.enclosingType(variable));
      if (ownInstanceField) {
        context.builder.accessOwnField(element.getSimpleName().toString());
      }
    }
    return super.visitIdentifier(tree, unused);
  }

  @Override
  public Void visitSwitch(SwitchTree tree, Void unused) {
    recordSwitch(tree.getExpression(), tree.getCases(), tree);
    return super.visitSwitch(tree, unused);
  }

  @Override
  public Void visitSwitchExpression(SwitchExpressionTree tree, Void unused) {
    recordSwitch(tree.getExpression(), tree.getCases(), tree);
    return super.visitSwitchExpression(tree, unused);
  }

  private void recordSwitch(
      ExpressionTree selector, List<? extends CaseTree> cases, Tree switchTree) {
    MethodContext context = methodStack.peek();
    ClassContext classContext = classStack.peek();
    if (context == null || classContext == null) return;
    TreePath selectorPath = TreePath.getPath(getCurrentPath(), BodySyntax.unwrap(selector));
    if (selectorPath == null) return;
    TypeMirror mirror = trees.getTypeMirror(selectorPath);
    if (!(mirror instanceof DeclaredType declared)
        || declared.asElement().getKind() != ElementKind.ENUM) {
      return;
    }
    BodySyntax.RawSwitch described = BodySyntax.describeCases(cases);
    program.addEnumSwitch(
        new dev.tenet.facts.SwitchOverEnum(
            new TypeName(((TypeElement) declared.asElement()).getQualifiedName().toString()),
            classContext.name(),
            context.id,
            described.coveredConstants(),
            described.hasDefault(),
            described.defaultThrows(),
            refOf(switchTree)));
  }

  @Override
  public Void visitAnnotation(AnnotationTree tree, Void unused) {
    annotationDepth++;
    Void result = super.visitAnnotation(tree, unused);
    annotationDepth--;
    return result;
  }

  @Override
  public Void visitLiteral(LiteralTree tree, Void unused) {
    if (annotationDepth == 0 && methodStack.peek() != null && !underConstantDefinition()) {
      Object value = tree.getValue();
      if (value instanceof String text && text.length() >= 5) {
        program.addLiteral("\"" + text + "\"", refOf(tree));
      } else if (value instanceof Number number && Math.abs(number.longValue()) >= 60) {
        program.addLiteral(String.valueOf(number), refOf(tree));
      }
    }
    return super.visitLiteral(tree, unused);
  }

  private boolean underConstantDefinition() {
    for (TreePath path = getCurrentPath(); path != null; path = path.getParentPath()) {
      if (path.getLeaf() instanceof VariableTree declared && isConstant(declared.getModifiers())) {
        return true;
      }
      if (path.getLeaf() instanceof CaseTree) return true;
    }
    return false;
  }

  private boolean isConstant(ModifiersTree modifiers) {
    var flags = modifiers.getFlags();
    return flags.contains(Modifier.STATIC) && flags.contains(Modifier.FINAL);
  }

  private void recordTenetSuppressions(SuppressWarnings annotation, Tree tree) {
    if (annotation == null) return;
    Set<String> rules = new LinkedHashSet<>();
    boolean tenetScoped = false;
    for (String value : annotation.value()) {
      if (value.equals("tenet")) {
        tenetScoped = true;
        rules.clear();
        break;
      }
      if (value.startsWith("tenet:")) {
        tenetScoped = true;
        rules.add(value.substring("tenet:".length()));
      }
    }
    if (tenetScoped) {
      program.addSuppression(new SuppressionScope(fileName, lineOf(tree), endLineOf(tree), rules));
    }
  }

  private Visibility visibilityOf(Set<Modifier> modifiers) {
    if (modifiers.contains(Modifier.PUBLIC)) return Visibility.PUBLIC;
    if (modifiers.contains(Modifier.PROTECTED)) return Visibility.PROTECTED;
    if (modifiers.contains(Modifier.PRIVATE)) return Visibility.PRIVATE;
    return Visibility.PACKAGE_PRIVATE;
  }

  private boolean hasAnnotation(ModifiersTree modifiers, String simpleName) {
    return modifiers != null
        && modifiers.getAnnotations().stream()
            .anyMatch(annotation -> annotation.getAnnotationType().toString().endsWith(simpleName));
  }

  private boolean hasSuppressUnchecked(ModifiersTree modifiers) {
    return modifiers != null
        && modifiers.getAnnotations().stream()
            .anyMatch(
                annotation ->
                    annotation.getAnnotationType().toString().endsWith("SuppressWarnings")
                        && annotation.toString().contains("unchecked"));
  }

  private SourceRef refOf(Tree tree) {
    return new SourceRef(fileName, lineOf(tree));
  }

  private long lineOf(Tree tree) {
    long position = positions.getStartPosition(unit, tree);
    return position < 0 ? 0 : unit.getLineMap().getLineNumber(position);
  }

  private long endLineOf(Tree tree) {
    long position = positions.getEndPosition(unit, tree);
    return position < 0 ? 0 : unit.getLineMap().getLineNumber(position);
  }

  private record ClassContext(
      TypeElement element, ClassFacts.Builder builder, Map<String, FieldFacts> fieldsByName) {

    private ClassContext(TypeElement element, ClassFacts.Builder builder) {
      this(element, builder, new LinkedHashMap<>());
    }

    private TypeName name() {
      return new TypeName(element.getQualifiedName().toString());
    }

    private Set<String> collectionFieldNames() {
      Set<String> names = new LinkedHashSet<>();
      fieldsByName.forEach(
          (name, facts) -> {
            if (facts.isMutableCollection()) names.add(name);
          });
      return names;
    }
  }

  private static final class MethodContext {
    private final ExecutableElement element;
    private final MethodId id;
    private final MethodFacts.Builder builder;
    private final boolean isCtor;
    private final Set<String> booleanParams;
    private final Set<String> newLocals = new LinkedHashSet<>();
    private final List<RecordedCall> calls = new ArrayList<>();

    private MethodContext(
        ExecutableElement element,
        MethodId id,
        MethodFacts.Builder builder,
        boolean isCtor,
        Set<String> booleanParams) {
      this.element = element;
      this.id = id;
      this.builder = builder;
      this.isCtor = isCtor;
      this.booleanParams = booleanParams;
    }
  }

  private record RecordedCall(
      long line, Optional<MethodId> inRepo, Optional<ExternalCall> external) {

    private static RecordedCall inRepo(long line, MethodId id) {
      return new RecordedCall(line, Optional.of(id), Optional.empty());
    }

    private static RecordedCall external(long line, ExternalCall call) {
      return new RecordedCall(line, Optional.empty(), Optional.of(call));
    }
  }
}
