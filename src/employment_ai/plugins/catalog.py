from __future__ import annotations

from employment_ai.core.contracts import Plugin
from employment_ai.plugins.data_quality import DataQualityPlugin
from employment_ai.plugins.excel_source import ExcelSourcePlugin
from employment_ai.plugins.llm_provider import LlmProviderPlugin
from employment_ai.plugins.matching import ExplanationPlugin, RuleFilterPlugin, SemanticRankerPlugin
from employment_ai.plugins.ontology import SemanticOntologyPlugin
from employment_ai.plugins.workflow import (
    FeedbackMetricsPlugin,
    MatchExportPlugin,
    ReviewWorkflowPlugin,
)


def built_in_plugins() -> list[Plugin]:
    return [
        DataQualityPlugin(),
        SemanticOntologyPlugin(),
        ExcelSourcePlugin(),
        RuleFilterPlugin(),
        ExplanationPlugin(),
        LlmProviderPlugin(),
        SemanticRankerPlugin(),
        ReviewWorkflowPlugin(),
        FeedbackMetricsPlugin(),
        MatchExportPlugin(),
    ]
