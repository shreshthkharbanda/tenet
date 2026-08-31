package dev.tenet.rules;

import dev.tenet.analysis.Analysis;
import dev.tenet.model.Finding;
import dev.tenet.model.RuleDescriptor;
import java.util.List;

public interface Rule {

  RuleDescriptor descriptor();

  List<Finding> evaluate(Analysis analysis);
}
