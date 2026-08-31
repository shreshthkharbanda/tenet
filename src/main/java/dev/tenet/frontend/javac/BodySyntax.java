package dev.tenet.frontend.javac;

import com.sun.source.tree.BlockTree;
import com.sun.source.tree.CaseTree;
import com.sun.source.tree.CatchTree;
import com.sun.source.tree.ExpressionStatementTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.IfTree;
import com.sun.source.tree.LiteralTree;
import com.sun.source.tree.MemberSelectTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.NewClassTree;
import com.sun.source.tree.ParenthesizedTree;
import com.sun.source.tree.ReturnTree;
import com.sun.source.tree.StatementTree;
import com.sun.source.tree.ThrowTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.TryTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.TreeScanner;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.ToLongFunction;

final class BodySyntax {

  private static final int MIN_HASHED_STATEMENTS = 4;
  private static final Set<String> BROAD_EXCEPTIONS =
      Set.of("Exception", "RuntimeException", "Throwable");
  private static final Set<String> LOG_METHOD_NAMES =
      Set.of("info", "warn", "error", "debug", "trace", "log", "println", "printStackTrace");
  private static final Set<String> MAP_CHECK_NAMES =
      Set.of("containsKey", "containsValue", "contains");
  private static final Set<String> MUTATOR_NAMES =
      Set.of("put", "add", "remove", "putAll", "addAll", "clear", "set");

  private BodySyntax() {}

  record Shape(
      int statementCount,
      int maxNesting,
      long invertibleGuardLine,
      boolean returnsThis,
      boolean trivialAccessor,
      boolean throwsUnsupportedOnly) {}

  static Shape shape(MethodTree method, ToLongFunction<Tree> line) {
    BlockTree body = method.getBody();
    if (body == null) {
      return new Shape(0, 0, 0, false, false, false);
    }
    NestingScanner nesting = new NestingScanner();
    nesting.scan(body, null);
    long guardLine = nesting.maxDepth > 3 ? findInvertibleGuard(body, line) : 0;
    return new Shape(
        countStatements(body),
        nesting.maxDepth,
        guardLine,
        returnsThis(body),
        isTrivialAccessor(body),
        throwsUnsupportedOnly(body));
  }

  private static int countStatements(BlockTree body) {
    StatementCounter counter = new StatementCounter();
    counter.scan(body, null);
    return counter.count;
  }

  private static boolean returnsThis(BlockTree body) {
    ReturnThisScanner scanner = new ReturnThisScanner();
    scanner.scan(body, null);
    return scanner.found;
  }

  private static boolean isTrivialAccessor(BlockTree body) {
    if (body.getStatements().size() != 1) return false;
    StatementTree only = body.getStatements().get(0);
    if (only instanceof ReturnTree ret && ret.getExpression() != null) {
      ExpressionTree expr = unwrap(ret.getExpression());
      return expr instanceof IdentifierTree
          || (expr instanceof MemberSelectTree select && isThis(select.getExpression()));
    }
    if (only instanceof ExpressionStatementTree stmt
        && stmt.getExpression() instanceof com.sun.source.tree.AssignmentTree assign) {
      return unwrap(assign.getExpression()) instanceof IdentifierTree;
    }
    return false;
  }

  private static boolean throwsUnsupportedOnly(BlockTree body) {
    if (body.getStatements().size() != 1) return false;
    return isThrowOf(body.getStatements().get(0), "UnsupportedOperationException");
  }

  private static boolean isThrowOf(StatementTree statement, String exceptionSimpleName) {
    return statement instanceof ThrowTree thrown
        && unwrap(thrown.getExpression()) instanceof NewClassTree created
        && created.getIdentifier().toString().endsWith(exceptionSimpleName);
  }

  private static long findInvertibleGuard(BlockTree body, ToLongFunction<Tree> line) {
    GuardScanner scanner = new GuardScanner(line);
    scanner.scan(body, null);
    return scanner.guardLine;
  }

  static boolean terminates(StatementTree statement) {
    if (statement == null) return false;
    if (statement instanceof ReturnTree || statement instanceof ThrowTree) return true;
    if (statement instanceof BlockTree block) {
      List<? extends StatementTree> statements = block.getStatements();
      return !statements.isEmpty() && terminates(statements.get(statements.size() - 1));
    }
    if (statement instanceof IfTree branch) {
      return branch.getElseStatement() != null
          && terminates(branch.getThenStatement())
          && terminates(branch.getElseStatement());
    }
    return false;
  }

  static Optional<String> booleanFlagParam(MethodTree method, Set<String> booleanParamNames) {
    BlockTree body = method.getBody();
    if (body == null || booleanParamNames.isEmpty()) return Optional.empty();
    List<? extends StatementTree> statements = body.getStatements();
    boolean coversBody =
        statements.size() == 1
            || (statements.size() == 2 && statements.get(1) instanceof ReturnTree);
    if (!coversBody || !(statements.get(0) instanceof IfTree branch)) return Optional.empty();
    ExpressionTree condition = unwrap(branch.getCondition());
    if (!(condition instanceof IdentifierTree ident)) return Optional.empty();
    String name = ident.getName().toString();
    if (!booleanParamNames.contains(name)) return Optional.empty();
    return countIdentifierUses(body, name) == 1 ? Optional.of(name) : Optional.empty();
  }

  private static int countIdentifierUses(Tree tree, String name) {
    IdentifierCounter counter = new IdentifierCounter(name);
    counter.scan(tree, null);
    return counter.count;
  }

  record BranchAssignedLocal(String name, long line) {}

  static List<BranchAssignedLocal> branchAssignedLocals(
      MethodTree method, ToLongFunction<Tree> line) {
    List<BranchAssignedLocal> result = new ArrayList<>();
    new BlockPairScanner() {
      @Override
      void onPair(StatementTree first, StatementTree second) {
        if (!(first instanceof VariableTree declared) || declared.getInitializer() != null) return;
        if (!(second instanceof IfTree branch) || branch.getElseStatement() == null) return;
        String name = declared.getName().toString();
        if (assignsOnly(branch.getThenStatement(), name)
            && assignsOnly(branch.getElseStatement(), name)) {
          result.add(new BranchAssignedLocal(name, line.applyAsLong(declared)));
        }
      }
    }.scan(method.getBody(), null);
    return result;
  }

  private static boolean assignsOnly(StatementTree arm, String name) {
    StatementTree effective = arm;
    if (arm instanceof BlockTree block && block.getStatements().size() == 1) {
      effective = block.getStatements().get(0);
    }
    return effective instanceof ExpressionStatementTree stmt
        && stmt.getExpression() instanceof com.sun.source.tree.AssignmentTree assign
        && assign.getVariable() instanceof IdentifierTree ident
        && ident.getName().contentEquals(name);
  }

  enum Disposal {
    EMPTY,
    LOG_ONLY,
    RETURNS_DEFAULT,
    RETHROWS,
    HANDLES
  }

  record RawCatch(
      String typeText, Disposal disposal, boolean interrupted, boolean reinterrupts, long line) {}

  static List<RawCatch> catches(MethodTree method, ToLongFunction<Tree> line) {
    List<RawCatch> result = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitTry(TryTree tree, Void unused) {
        for (CatchTree caught : tree.getCatches()) {
          result.add(describeCatch(caught, line));
        }
        return super.visitTry(tree, unused);
      }
    }.scan(method.getBody(), null);
    return result;
  }

  private static RawCatch describeCatch(CatchTree caught, ToLongFunction<Tree> line) {
    String typeText = caught.getParameter().getType().toString();
    boolean interrupted = typeText.contains("InterruptedException");
    boolean reinterrupts = containsCallNamed(caught.getBlock(), "interrupt");
    return new RawCatch(
        typeText,
        disposalOf(caught.getBlock()),
        interrupted,
        reinterrupts,
        line.applyAsLong(caught));
  }

  private static Disposal disposalOf(BlockTree block) {
    List<? extends StatementTree> statements = block.getStatements();
    if (statements.isEmpty()) return Disposal.EMPTY;
    if (statements.stream().allMatch(BodySyntax::isLogStatement)) return Disposal.LOG_ONLY;
    StatementTree last = statements.get(statements.size() - 1);
    if (last instanceof ThrowTree) return Disposal.RETHROWS;
    if (last instanceof ReturnTree ret && isDefaultLiteral(ret.getExpression())) {
      return Disposal.RETURNS_DEFAULT;
    }
    return Disposal.HANDLES;
  }

  private static boolean isLogStatement(StatementTree statement) {
    return statement instanceof ExpressionStatementTree stmt
        && unwrap(stmt.getExpression()) instanceof MethodInvocationTree call
        && LOG_METHOD_NAMES.contains(invokedName(call));
  }

  private static boolean isDefaultLiteral(ExpressionTree expression) {
    if (expression == null) return false;
    ExpressionTree unwrapped = unwrap(expression);
    if (!(unwrapped instanceof LiteralTree literal)) return false;
    Object value = literal.getValue();
    return value == null || Boolean.FALSE.equals(value) || Integer.valueOf(0).equals(value);
  }

  record RawCheckAct(String receiver, String checkCall, String actCall, long line) {}

  static List<RawCheckAct> checkThenActs(
      MethodTree method, Set<String> fieldNames, ToLongFunction<Tree> line) {
    List<RawCheckAct> result = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitIf(IfTree tree, Void unused) {
        checkOne(tree, fieldNames, line).ifPresent(result::add);
        return super.visitIf(tree, unused);
      }
    }.scan(method.getBody(), null);
    return result;
  }

  private static Optional<RawCheckAct> checkOne(
      IfTree branch, Set<String> fieldNames, ToLongFunction<Tree> line) {
    Optional<MethodInvocationTree> check =
        findInvocation(unwrap(branch.getCondition()), MAP_CHECK_NAMES);
    if (check.isEmpty()) return Optional.empty();
    Optional<String> receiver = receiverName(check.get());
    if (receiver.isEmpty() || !fieldNames.contains(receiver.get())) return Optional.empty();
    Optional<MethodInvocationTree> act = findMutatorOn(branch.getThenStatement(), receiver.get());
    return act.map(
        mutator ->
            new RawCheckAct(
                receiver.get(),
                displayCall(receiver.get() + "." + invokedName(check.get())),
                displayCall(receiver.get() + "." + invokedName(mutator)),
                line.applyAsLong(branch)));
  }

  private static Optional<MethodInvocationTree> findInvocation(Tree tree, Set<String> names) {
    List<MethodInvocationTree> matches = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitMethodInvocation(MethodInvocationTree call, Void unused) {
        if (names.contains(invokedName(call))) matches.add(call);
        return super.visitMethodInvocation(call, unused);
      }
    }.scan(tree, null);
    return matches.stream().findFirst();
  }

  private static Optional<MethodInvocationTree> findMutatorOn(StatementTree arm, String receiver) {
    List<MethodInvocationTree> matches = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitMethodInvocation(MethodInvocationTree call, Void unused) {
        boolean mutates =
            MUTATOR_NAMES.contains(invokedName(call))
                && receiverName(call).map(receiver::equals).orElse(false);
        if (mutates) matches.add(call);
        return super.visitMethodInvocation(call, unused);
      }
    }.scan(arm, null);
    return matches.stream().findFirst();
  }

  record RawRetryLoop(
      long loopLine,
      boolean bounded,
      boolean classifiedErrors,
      boolean hasSleep,
      boolean sleepGrows,
      long tryStartLine,
      long tryEndLine) {}

  static List<RawRetryLoop> retryLoops(
      MethodTree method, ToLongFunction<Tree> startLine, ToLongFunction<Tree> endLine) {
    List<RawRetryLoop> result = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitWhileLoop(com.sun.source.tree.WhileLoopTree tree, Void unused) {
        describeLoop(tree, tree.getCondition(), tree.getStatement(), startLine, endLine, result);
        return super.visitWhileLoop(tree, unused);
      }

      @Override
      public Void visitForLoop(com.sun.source.tree.ForLoopTree tree, Void unused) {
        describeLoop(tree, tree.getCondition(), tree.getStatement(), startLine, endLine, result);
        return super.visitForLoop(tree, unused);
      }

      @Override
      public Void visitDoWhileLoop(com.sun.source.tree.DoWhileLoopTree tree, Void unused) {
        describeLoop(tree, tree.getCondition(), tree.getStatement(), startLine, endLine, result);
        return super.visitDoWhileLoop(tree, unused);
      }
    }.scan(method.getBody(), null);
    return result;
  }

  private static void describeLoop(
      Tree loop,
      ExpressionTree condition,
      StatementTree loopBody,
      ToLongFunction<Tree> startLine,
      ToLongFunction<Tree> endLine,
      List<RawRetryLoop> result) {
    Optional<TryTree> tryTree = findTry(loopBody);
    if (tryTree.isEmpty() || tryTree.get().getCatches().isEmpty()) return;
    boolean classified =
        tryTree.get().getCatches().stream()
            .noneMatch(
                caught ->
                    BROAD_EXCEPTIONS.contains(
                        simpleName(caught.getParameter().getType().toString())));
    Optional<MethodInvocationTree> sleep = findSleep(loopBody);
    boolean sleepGrows =
        sleep
            .map(
                call ->
                    !call.getArguments().isEmpty()
                        && !(unwrap(call.getArguments().get(0)) instanceof LiteralTree))
            .orElse(false);
    result.add(
        new RawRetryLoop(
            startLine.applyAsLong(loop),
            conditionLooksBounded(condition),
            classified,
            sleep.isPresent(),
            sleepGrows,
            startLine.applyAsLong(tryTree.get()),
            endLine.applyAsLong(tryTree.get())));
  }

  private static Optional<TryTree> findTry(StatementTree loopBody) {
    List<TryTree> matches = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitTry(TryTree tree, Void unused) {
        matches.add(tree);
        return null;
      }
    }.scan(loopBody, null);
    return matches.stream().findFirst();
  }

  private static Optional<MethodInvocationTree> findSleep(StatementTree loopBody) {
    List<MethodInvocationTree> matches = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitMethodInvocation(MethodInvocationTree call, Void unused) {
        if (invokedName(call).equals("sleep")) matches.add(call);
        return super.visitMethodInvocation(call, unused);
      }
    }.scan(loopBody, null);
    return matches.stream().findFirst();
  }

  private static boolean conditionLooksBounded(ExpressionTree condition) {
    if (condition == null) return false;
    List<LiteralTree> numericLiterals = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitLiteral(LiteralTree literal, Void unused) {
        if (literal.getValue() instanceof Number) numericLiterals.add(literal);
        return null;
      }
    }.scan(unwrap(condition), null);
    return !numericLiterals.isEmpty();
  }

  record InvocationDecl(String varName, String callText, long line, Set<String> identifiersUsed) {}

  static List<List<InvocationDecl>> consecutiveInvocationDecls(
      MethodTree method, ToLongFunction<Tree> line) {
    List<List<InvocationDecl>> runs = new ArrayList<>();
    new BlockPairScanner() {
      @Override
      void onPair(StatementTree first, StatementTree second) {
        Optional<InvocationDecl> left = asInvocationDecl(first, line);
        Optional<InvocationDecl> right = asInvocationDecl(second, line);
        if (left.isPresent() && right.isPresent()) {
          runs.add(List.of(left.get(), right.get()));
        }
      }
    }.scan(method.getBody(), null);
    return runs;
  }

  private static Optional<InvocationDecl> asInvocationDecl(
      StatementTree statement, ToLongFunction<Tree> line) {
    if (!(statement instanceof VariableTree declared)) return Optional.empty();
    ExpressionTree init = declared.getInitializer();
    if (init == null || !(unwrap(init) instanceof MethodInvocationTree call))
      return Optional.empty();
    Set<String> used = new HashSet<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitIdentifier(IdentifierTree ident, Void unused) {
        used.add(ident.getName().toString());
        return null;
      }
    }.scan(call, null);
    return Optional.of(
        new InvocationDecl(
            declared.getName().toString(),
            call.getMethodSelect().toString(),
            line.applyAsLong(declared),
            used));
  }

  static Optional<String> bodyHash(MethodTree method) {
    BlockTree body = method.getBody();
    if (body == null || countStatements(body) < MIN_HASHED_STATEMENTS) return Optional.empty();
    Set<String> declared = declaredNames(method);
    StringBuilder canonical = new StringBuilder();
    Map<String, Integer> alpha = new LinkedHashMap<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void scan(Tree tree, Void unused) {
        if (tree != null) canonical.append('(').append(tree.getKind().name());
        Void result = super.scan(tree, unused);
        if (tree != null) canonical.append(')');
        return result;
      }

      @Override
      public Void visitIdentifier(IdentifierTree ident, Void unused) {
        String name = ident.getName().toString();
        if (declared.contains(name)) {
          canonical.append("v").append(alpha.computeIfAbsent(name, key -> alpha.size()));
        } else {
          canonical.append(name);
        }
        return null;
      }

      @Override
      public Void visitLiteral(LiteralTree literal, Void unused) {
        canonical.append(String.valueOf(literal.getValue()));
        return null;
      }

      @Override
      public Void visitMemberSelect(MemberSelectTree select, Void unused) {
        canonical.append('.').append(select.getIdentifier());
        return super.visitMemberSelect(select, unused);
      }
    }.scan(body, null);
    return Optional.of(sha256(canonical.toString()));
  }

  private static Set<String> declaredNames(MethodTree method) {
    Set<String> names = new HashSet<>();
    method.getParameters().forEach(param -> names.add(param.getName().toString()));
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitVariable(VariableTree declared, Void unused) {
        names.add(declared.getName().toString());
        return super.visitVariable(declared, unused);
      }
    }.scan(method.getBody(), null);
    return names;
  }

  private static String sha256(String canonical) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hashed = digest.digest(canonical.getBytes(StandardCharsets.UTF_8));
      StringBuilder hex = new StringBuilder(hashed.length * 2);
      for (byte b : hashed) {
        hex.append(String.format(Locale.ROOT, "%02x", b));
      }
      return hex.toString();
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 is a mandatory JDK algorithm", e);
    }
  }

  record RawSwitch(List<String> coveredConstants, boolean hasDefault, boolean defaultThrows) {}

  static RawSwitch describeCases(List<? extends CaseTree> cases) {
    List<String> covered = new ArrayList<>();
    boolean hasDefault = false;
    boolean defaultThrows = false;
    for (CaseTree caseTree : cases) {
      for (com.sun.source.tree.CaseLabelTree label : caseTree.getLabels()) {
        if (label instanceof com.sun.source.tree.DefaultCaseLabelTree) {
          hasDefault = true;
          defaultThrows = caseThrows(caseTree);
        } else if (label instanceof com.sun.source.tree.ConstantCaseLabelTree constant
            && constant.getConstantExpression() instanceof IdentifierTree ident) {
          covered.add(ident.getName().toString());
        }
      }
    }
    return new RawSwitch(covered, hasDefault, defaultThrows);
  }

  private static boolean caseThrows(CaseTree caseTree) {
    if (caseTree.getBody() instanceof ThrowTree) return true;
    if (caseTree.getBody() instanceof BlockTree block) return terminatesWithThrow(block);
    List<? extends StatementTree> statements = caseTree.getStatements();
    return statements != null
        && !statements.isEmpty()
        && statements.get(statements.size() - 1) instanceof ThrowTree;
  }

  private static boolean terminatesWithThrow(BlockTree block) {
    List<? extends StatementTree> statements = block.getStatements();
    return !statements.isEmpty() && statements.get(statements.size() - 1) instanceof ThrowTree;
  }

  static String displayCall(String base) {
    return base + "(...)";
  }

  static ExpressionTree unwrap(ExpressionTree expression) {
    ExpressionTree current = expression;
    while (current instanceof ParenthesizedTree parenthesized) {
      current = parenthesized.getExpression();
    }
    return current;
  }

  static String invokedName(MethodInvocationTree call) {
    ExpressionTree select = call.getMethodSelect();
    if (select instanceof MemberSelectTree member) return member.getIdentifier().toString();
    if (select instanceof IdentifierTree ident) return ident.getName().toString();
    return "";
  }

  static Optional<String> receiverName(MethodInvocationTree call) {
    if (!(call.getMethodSelect() instanceof MemberSelectTree member)) return Optional.empty();
    ExpressionTree base = unwrap(member.getExpression());
    if (base instanceof IdentifierTree ident) return Optional.of(ident.getName().toString());
    if (base instanceof MemberSelectTree thisSelect && isThis(thisSelect.getExpression())) {
      return Optional.of(thisSelect.getIdentifier().toString());
    }
    return Optional.empty();
  }

  static boolean isThis(ExpressionTree expression) {
    return unwrap(expression) instanceof IdentifierTree ident
        && ident.getName().contentEquals("this");
  }

  static boolean containsCallNamed(Tree tree, String name) {
    List<MethodInvocationTree> matches = new ArrayList<>();
    new TreeScanner<Void, Void>() {
      @Override
      public Void visitMethodInvocation(MethodInvocationTree call, Void unused) {
        if (invokedName(call).equals(name)) matches.add(call);
        return super.visitMethodInvocation(call, unused);
      }
    }.scan(tree, null);
    return !matches.isEmpty();
  }

  private static String simpleName(String typeText) {
    int lastDot = typeText.lastIndexOf('.');
    return lastDot < 0 ? typeText : typeText.substring(lastDot + 1);
  }

  private static final class StatementCounter extends TreeScanner<Void, Void> {
    private int count;

    @Override
    public Void scan(Tree tree, Void unused) {
      if (tree instanceof StatementTree && !(tree instanceof BlockTree)) count++;
      return super.scan(tree, unused);
    }
  }

  private static final class NestingScanner extends TreeScanner<Void, Void> {
    private int depth;
    private int maxDepth;

    @Override
    public Void scan(Tree tree, Void unused) {
      boolean nests =
          tree instanceof IfTree
              || tree instanceof com.sun.source.tree.ForLoopTree
              || tree instanceof com.sun.source.tree.EnhancedForLoopTree
              || tree instanceof com.sun.source.tree.WhileLoopTree
              || tree instanceof com.sun.source.tree.DoWhileLoopTree
              || tree instanceof com.sun.source.tree.SwitchTree
              || tree instanceof TryTree;
      if (nests) {
        depth++;
        maxDepth = Math.max(maxDepth, depth);
      }
      Void result = super.scan(tree, unused);
      if (nests) depth--;
      return result;
    }
  }

  private static final class GuardScanner extends TreeScanner<Void, Void> {
    private final ToLongFunction<Tree> line;
    private int depth;
    private long guardLine;

    private GuardScanner(ToLongFunction<Tree> line) {
      this.line = line;
    }

    @Override
    public Void visitIf(IfTree tree, Void unused) {
      boolean invertible =
          guardLine == 0
              && depth <= 2
              && (terminates(tree.getThenStatement())
                  || (tree.getElseStatement() != null && terminates(tree.getElseStatement())));
      if (invertible) guardLine = line.applyAsLong(tree);
      depth++;
      Void result = super.visitIf(tree, unused);
      depth--;
      return result;
    }
  }

  private static final class ReturnThisScanner extends TreeScanner<Void, Void> {
    private boolean found;

    @Override
    public Void visitReturn(ReturnTree tree, Void unused) {
      if (tree.getExpression() != null && isThis(tree.getExpression())) found = true;
      return super.visitReturn(tree, unused);
    }
  }

  private static final class IdentifierCounter extends TreeScanner<Void, Void> {
    private final String name;
    private int count;

    private IdentifierCounter(String name) {
      this.name = name;
    }

    @Override
    public Void visitIdentifier(IdentifierTree tree, Void unused) {
      if (tree.getName().contentEquals(name)) count++;
      return null;
    }
  }

  private abstract static class BlockPairScanner extends TreeScanner<Void, Void> {
    abstract void onPair(StatementTree first, StatementTree second);

    @Override
    public Void visitBlock(BlockTree block, Void unused) {
      List<? extends StatementTree> statements = block.getStatements();
      for (int i = 0; i + 1 < statements.size(); i++) {
        onPair(statements.get(i), statements.get(i + 1));
      }
      return super.visitBlock(block, unused);
    }
  }
}
