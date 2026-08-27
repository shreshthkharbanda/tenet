package io.tenet.analysis;

import javax.lang.model.element.Element;
import java.util.Set;

record MethodUsage(Element method, Set<Element> fields, Set<Element> calls) {
    MethodUsage {
        fields = Set.copyOf(fields);
        calls = Set.copyOf(calls);
    }
}
