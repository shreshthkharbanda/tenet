package io.tenet.analysis;

import io.tenet.model.RuleId;

record Violation(
        RuleId rule,
        JavaSource source,
        Location location,
        String message,
        String evidence) {
}

