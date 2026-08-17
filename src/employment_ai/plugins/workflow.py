from __future__ import annotations

import csv
import io
from typing import Any

from employment_ai.core.context import AppContext
from employment_ai.core.contracts import Plugin, PluginManifest

REVIEW_DECISIONS = {"accepted", "rejected", "needs_review"}
FEEDBACK_OUTCOMES = {"effective", "ineffective", "not_contacted", "declined", "follow_up"}


class ReviewWorkflowService:
    def __init__(self, context: AppContext) -> None:
        self.context = context

    def review(self, match_id: str, decision: str, reason: str, actor: str) -> dict[str, str]:
        if decision not in REVIEW_DECISIONS:
            raise ValueError("审核决定无效")
        if not self.context.db.match_exists(match_id):
            raise ValueError("匹配记录不存在")
        if decision in {"rejected", "needs_review"} and not reason.strip():
            raise ValueError("驳回或待复核必须填写理由")
        review_id = self.context.db.add_review(match_id, decision, reason.strip(), actor)
        self.context.events.publish("review.recorded", {"match_id": match_id, "decision": decision})
        self.context.audit("review.recorded", actor, {"match_id": match_id, "decision": decision})
        return {"review_id": review_id, "match_id": match_id, "decision": decision}


class FeedbackMetricsService:
    def __init__(self, context: AppContext) -> None:
        self.context = context

    def record(self, match_id: str, outcome: str, reason: str, actor: str) -> dict[str, str]:
        if outcome not in FEEDBACK_OUTCOMES:
            raise ValueError("反馈结果无效")
        if not self.context.db.match_exists(match_id):
            raise ValueError("匹配记录不存在")
        feedback_id = self.context.db.add_feedback(match_id, outcome, reason.strip(), actor)
        self.context.events.publish("feedback.recorded", {"match_id": match_id, "outcome": outcome})
        self.context.audit("feedback.recorded", actor, {"match_id": match_id, "outcome": outcome})
        return {"feedback_id": feedback_id, "match_id": match_id, "outcome": outcome}

    def metrics(self, batch_id: str) -> dict[str, Any]:
        return self.context.db.metrics(batch_id)


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


class MatchExportService:
    def __init__(self, context: AppContext) -> None:
        self.context = context

    def export_csv(self, batch_id: str, job_id: str, actor: str) -> str:
        rows = self.context.db.list_matches(batch_id, job_id)
        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow(
            [
                "rank",
                "person_id",
                "score",
                "rule_score",
                "semantic_score",
                "positives",
                "conflicts",
                "review_decision",
                "review_reason",
                "feedback_outcome",
                "model_version",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["rank_no"],
                    _csv_safe(row["person_id"]),
                    row["score"],
                    row["rule_score"],
                    row["semantic_score"],
                    _csv_safe("；".join(row["explanation"].get("positives", []))),
                    _csv_safe("；".join(row["explanation"].get("conflicts", []))),
                    row.get("review_decision") or "",
                    _csv_safe(row.get("review_reason") or ""),
                    row.get("feedback_outcome") or "",
                    row["model_version"],
                ]
            )
        self.context.audit(
            "match.exported", actor, {"batch_id": batch_id, "job_id": job_id, "rows": len(rows)}
        )
        return output.getvalue()


class ReviewWorkflowPlugin(Plugin):
    manifest = PluginManifest(
        id="review-workflow",
        version="1.0.0",
        name="人工审核流程",
        description="记录通过、驳回、待复核及理由，AI不替代业务决定",
        provides=("review.workflow",),
        requires=("match.rank",),
        permissions=("match:read", "review:write"),
        events_in=("match.ranked",),
        events_out=("review.recorded",),
        cleanup_strategy="remove workflow service; preserve human decisions and audit history",
    )

    def install(self, context: AppContext) -> None:
        context.services.register(
            "review.workflow", self.manifest.id, ReviewWorkflowService(context)
        )


class FeedbackMetricsPlugin(Plugin):
    manifest = PluginManifest(
        id="feedback-metrics",
        version="1.0.0",
        name="反馈与指标",
        description="记录触达结果并计算审核率、反馈完整率和接受率",
        provides=("feedback.metrics",),
        requires=("review.workflow",),
        permissions=("match:read", "feedback:write", "metrics:read"),
        events_in=("review.recorded",),
        events_out=("feedback.recorded",),
        cleanup_strategy="remove feedback service; preserve historical feedback and metrics inputs",
    )

    def install(self, context: AppContext) -> None:
        context.services.register(
            "feedback.metrics", self.manifest.id, FeedbackMetricsService(context)
        )


class MatchExportPlugin(Plugin):
    manifest = PluginManifest(
        id="match-export",
        version="1.0.0",
        name="受控导出",
        description="导出当前岗位匹配、审核和反馈结果，防止CSV公式注入",
        provides=("export.matches",),
        requires=("feedback.metrics",),
        permissions=("match:read", "export:write"),
        cleanup_strategy=(
            "remove export endpoint service; exported copies remain outside system boundary"
        ),
    )

    def install(self, context: AppContext) -> None:
        context.services.register("export.matches", self.manifest.id, MatchExportService(context))
