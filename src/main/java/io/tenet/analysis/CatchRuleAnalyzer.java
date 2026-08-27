package io.tenet.analysis;

import com.sun.source.tree.CatchTree;
import io.tenet.model.RuleId;

import java.util.List;

final class CatchRuleAnalyzer {
    private CatchRuleAnalyzer() {
    }

    static void analyze(final CatchTree catchTree, final CompilationContext context) {
        if (catchTree.getBlock().getStatements().isEmpty()) {
            context.add(
                    RuleId.EMPTY_CATCH,
                    catchTree,
                    "A catch block must resolve, translate, or propagate the failure",
                    "caught=" + catchTree.getParameter().getType());
        }
        if (isGenericException(catchTree.getParameter().getType().toString())) {
            context.add(
                    RuleId.GENERIC_EXCEPTION,
                    catchTree.getParameter(),
                    "Catch the narrow failure type instead of `" + catchTree.getParameter().getType() + "`",
                    "generic catch destroys the failure contract");
        }
    }

    static boolean isGenericException(final String type) {
        return List.of("Exception", "java.lang.Exception", "Throwable", "java.lang.Throwable").contains(type);
    }
}

