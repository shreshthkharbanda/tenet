package io.tenet.analysis;

import com.sun.source.tree.BlockTree;

record MethodMetrics(
        int cyclomaticComplexity,
        int maximumNestingDepth,
        boolean nestedTernary) {
    static MethodMetrics calculate(final BlockTree body) {
        final CyclomaticComplexityScanner complexity = new CyclomaticComplexityScanner();
        final NestingDepthScanner nesting = new NestingDepthScanner();
        final NestedTernaryScanner ternary = new NestedTernaryScanner();
        complexity.scan(body, null);
        nesting.scan(body, null);
        ternary.scan(body, null);
        return new MethodMetrics(complexity.value(), nesting.maximum(), ternary.found());
    }
}
