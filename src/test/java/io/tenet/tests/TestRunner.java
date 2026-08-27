package io.tenet.tests;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class TestRunner {
    private TestRunner() {
    }

    public static void main(final String[] arguments) throws IOException {
        final List<String> failures = new ArrayList<>();
        for (final TestCase test : tests()) {
            try {
                test.body().run();
                System.out.println("pass " + test.name());
            } catch (final AssertionError failure) {
                failures.add(test.name() + ": " + failure.getMessage());
            }
        }
        if (!failures.isEmpty()) {
            throw new AssertionError(String.join("\n\n", failures));
        }
        System.out.println("passed " + tests().size() + " deterministic tests");
    }

    private static List<TestCase> tests() {
        return List.of(
                test("clean source", CommentAndCompilerTests::acceptsCleanSource),
                test("ordinary comment", CommentAndCompilerTests::rejectsOrdinaryComment),
                test("context record", CommentAndCompilerTests::acceptsOneContextRecord),
                test("context record limit", CommentAndCompilerTests::rejectsSecondContextRecord),
                test("literal markers", CommentAndCompilerTests::ignoresCommentMarkersInLiterals),
                test("block comment", CommentAndCompilerTests::rejectsBlockComment),
                test("compilation diagnostic", CommentAndCompilerTests::reportsCompilationFailure),
                test("wildcard import", CommentAndCompilerTests::rejectsWildcardImport),
                test("root exclusion", CommentAndCompilerTests::excludesGeneratedSourceAtProjectRoot),
                test("cyclomatic complexity", MetricRuleTests::rejectsComplexMethod),
                test("nesting depth", MetricRuleTests::rejectsDeepNesting),
                test("source budgets", MetricRuleTests::enforcesFileAndMethodBudgets),
                test("parameter count", MetricRuleTests::rejectsWideParameterSurface),
                test("boolean parameter", MetricRuleTests::rejectsBooleanParameter),
                test("final local", MetricRuleTests::requiresFinalStableLocals),
                test("explicit local type", MetricRuleTests::rejectsInferredLocalType),
                test("field rules", DesignRuleTests::rejectsMutableAndPublicFields),
                test("reasoned mutable state", DesignRuleTests::acceptsReasonedMutableState),
                test("unexplained mutable state", DesignRuleTests::rejectsUnexplainedMutableState),
                test("public surface", DesignRuleTests::limitsPublicSurface),
                test("interface surface", DesignRuleTests::limitsInterfaceSurface),
                test("type fan-out", DesignRuleTests::limitsTypeFanOut),
                test("inheritance depth", DesignRuleTests::limitsInheritanceDepth),
                test("failure contracts", DesignRuleTests::rejectsEmptyGenericCatch),
                test("nested ternary", DesignRuleTests::rejectsNestedTernary),
                test("string discriminator", DesignRuleTests::rejectsStringDiscriminator),
                test("variant branching", DesignRuleTests::centralizesVariantBranching),
                test("exact duplication", DesignRuleTests::detectsExactDuplication),
                test("structural clone", DesignRuleTests::detectsStructuralClone),
                test("cohesion", DesignRuleTests::detectsDisconnectedResponsibilities),
                test("package cycle", GraphAndOutputTests::rejectsPackageCycle),
                test("architecture boundary", GraphAndOutputTests::enforcesArchitectureBoundary),
                test("json output", GraphAndOutputTests::emitsJson),
                test("sarif output", GraphAndOutputTests::emitsSarif),
                test("stable ordering", GraphAndOutputTests::producesStableOrdering),
                test("cli commands", GraphAndOutputTests::handlesCliCommands));
    }

    private static TestCase test(final String name, final CheckedTest body) {
        return new TestCase(name, body);
    }

    private record TestCase(String name, CheckedTest body) {
    }

    @FunctionalInterface
    private interface CheckedTest {
        void run() throws IOException;
    }
}
