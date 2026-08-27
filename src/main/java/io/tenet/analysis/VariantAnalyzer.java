package io.tenet.analysis;

import io.tenet.config.TenetConfig;
import io.tenet.model.RuleId;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class VariantAnalyzer {
    private final TenetConfig config;
    private final ProjectFacts facts;

    public VariantAnalyzer(final TenetConfig config, final ProjectFacts facts) {
        this.config = config;
        this.facts = facts;
    }

    public void analyze() {
        final Map<String, List<SwitchSite>> sitesByType = new LinkedHashMap<>();
        for (final SwitchSite site : facts.switchSites()) {
            sitesByType.computeIfAbsent(site.typeName(), ignored -> new ArrayList<>()).add(site);
        }
        final int maximum = config.rules().integer("max.variantBranchSites");
        for (final Map.Entry<String, List<SwitchSite>> entry : sitesByType.entrySet()) {
            final List<SwitchSite> sites = entry.getValue();
            if (sites.size() <= maximum) {
                continue;
            }
            for (final SwitchSite site : sites) {
                facts.add(new Violation(
                        RuleId.VARIANT_BRANCHING,
                        site.source(),
                        site.location(),
                        "Enum `" + entry.getKey() + "` is branched on at " + sites.size() + " sites",
                        "maximum=" + maximum + "; move behavior behind one dispatch point"));
            }
        }
    }
}
