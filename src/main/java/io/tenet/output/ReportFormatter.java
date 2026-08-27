package io.tenet.output;

import io.tenet.model.AnalysisReport;

public interface ReportFormatter {
    String format(AnalysisReport report);
}

