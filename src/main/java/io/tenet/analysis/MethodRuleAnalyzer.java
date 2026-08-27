package io.tenet.analysis;

import com.sun.source.tree.MethodTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.Trees;
import io.tenet.model.RuleId;

import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;

final class MethodRuleAnalyzer {
    private final Trees trees;
    private final CompilationContext context;

    MethodRuleAnalyzer(final Trees trees, final CompilationContext context) {
        this.trees = trees;
        this.context = context;
    }

    void analyze(final TreePath methodPath, final MethodTree method, final TypeElement owner) {
        if (context.positions().getStartPosition(context.unit(), method) < 0) {
            return;
        }
        final boolean recordConstructor = owner.getKind() == ElementKind.RECORD && method.getReturnType() == null;
        if (!recordConstructor) {
            analyzeParameters(method);
        }
        analyzeThrownTypes(method);
        if (method.getBody() == null) {
            return;
        }
        final MethodMetrics metrics = MethodMetrics.calculate(method.getBody());
        analyzeMetrics(method, metrics);
        new LocalVariableAnalyzer(trees, context).analyze(
                methodPath,
                method,
                recordConstructor ? ParameterPolicy.EXCLUDE : ParameterPolicy.INCLUDE);
        addFingerprint(method, owner.getQualifiedName().toString());
    }

    private void analyzeParameters(final MethodTree method) {
        final int parameterCount = method.getParameters().size();
        final int maximum = context.config().rules().integer("max.parameters");
        if (parameterCount > maximum) {
            context.add(
                    RuleId.PARAMETER_COUNT,
                    method,
                    "Method accepts " + parameterCount + " parameters",
                    "maximum=" + maximum + "; introduce a value object");
        }
        for (final VariableTree parameter : method.getParameters()) {
            analyzeBooleanParameter(parameter);
        }
    }

    private void analyzeBooleanParameter(final VariableTree parameter) {
        if (parameter.getType().toString().equals("boolean")) {
            context.add(
                    RuleId.BOOLEAN_PARAMETER,
                    parameter,
                    "Replace boolean parameter `" + parameter.getName() + "` with separate operations or a named type",
                    "boolean parameters hide two behaviors");
        }
    }

    private void analyzeThrownTypes(final MethodTree method) {
        for (final com.sun.source.tree.ExpressionTree thrownType : method.getThrows()) {
            if (CatchRuleAnalyzer.isGenericException(thrownType.toString())) {
                context.add(
                        RuleId.GENERIC_EXCEPTION,
                        thrownType,
                        "Declare a narrow exception contract instead of `" + thrownType + "`",
                        "generic throws clause");
            }
        }
    }

    private void analyzeMetrics(final MethodTree method, final MethodMetrics metrics) {
        analyzeComplexity(method, metrics);
        analyzeNesting(method, metrics);
        analyzeLength(method);
        if (metrics.nestedTernary()) {
            context.add(
                    RuleId.NESTED_TERNARY,
                    method,
                    "Replace the nested ternary with named control flow",
                    "conditional expressions must not contain conditional expressions");
        }
    }

    private void analyzeComplexity(final MethodTree method, final MethodMetrics metrics) {
        final int maximum = context.config().rules().integer("max.cyclomaticComplexity");
        if (metrics.cyclomaticComplexity() > maximum) {
            context.add(
                    RuleId.CYCLOMATIC_COMPLEXITY,
                    method,
                    "Method has " + metrics.cyclomaticComplexity() + " independent control-flow paths",
                    "maximum=" + maximum);
        }
    }

    private void analyzeNesting(final MethodTree method, final MethodMetrics metrics) {
        final int maximum = context.config().rules().integer("max.nestingDepth");
        if (metrics.maximumNestingDepth() > maximum) {
            context.add(
                    RuleId.NESTING_DEPTH,
                    method,
                    "Method reaches nesting depth " + metrics.maximumNestingDepth(),
                    "maximum=" + maximum);
        }
    }

    private void analyzeLength(final MethodTree method) {
        final int lines = context.lineSpan(method);
        final int maximum = context.config().rules().integer("max.methodLines");
        if (lines > maximum) {
            context.add(
                    RuleId.METHOD_LENGTH,
                    method,
                    "Method spans " + lines + " lines",
                    "maximum=" + maximum);
        }
    }

    private void addFingerprint(final MethodTree method, final String owner) {
        final String body = method.getBody().toString();
        final StructuralFingerprint.Result structural = new StructuralFingerprint().calculate(method.getBody());
        context.facts().methodFingerprints().add(new MethodFingerprint(
                owner,
                method.getName().toString(),
                context.source(),
                Location.of(context.unit(), context.positions(), method),
                Hashing.sha256(body),
                structural.hash(),
                body.length(),
                structural.nodes()));
    }
}
