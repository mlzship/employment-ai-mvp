from __future__ import annotations

import uuid
from datetime import date
from difflib import SequenceMatcher
from typing import Any

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - deterministic fallback for constrained environments
    fuzz = None

from employment_ai.core.context import AppContext
from employment_ai.core.contracts import Plugin, PluginManifest
from employment_ai.plugins.data_quality import EDUCATION_LEVELS
from employment_ai.plugins.llm_provider import (
    CandidateSemanticAssessment,
    LlmProviderError,
    OpenAICompatibleLlmService,
)

EDUCATION_SCORE = {name: index for index, name in enumerate(EDUCATION_LEVELS)}
ELIGIBLE_STATUSES = {"求职中", "失业", "灵活就业"}
BASELINE_MODEL_VERSION = "hybrid-rule-local-v1.1"
LLM_MODEL_VERSION = "hybrid-rule-llm-v2.0"


class RuleFilterService:
    def evaluate(self, job: dict[str, Any], person: dict[str, Any]) -> dict[str, Any]:
        conflicts: list[str] = []
        factors: dict[str, float] = {}
        if job["status"] != "active" or date.fromisoformat(job["valid_until"]) < date.today():
            return {"eligible": False, "rule_score": 0.0, "factors": {}, "conflicts": ["岗位无效"]}
        if person["employment_status"] not in ELIGIBLE_STATUSES:
            return {
                "eligible": False,
                "rule_score": 0.0,
                "factors": {},
                "conflicts": ["当前就业状态不进入候选池"],
            }

        required = set(job.get("canonical_required_skills") or job["required_skills"])
        owned = set(person.get("canonical_skills") or person["skills"])
        skill_ratio = len(required & owned) / len(required) if required else 1.0
        factors["技能匹配"] = skill_ratio
        if skill_ratio < 0.34:
            conflicts.append("关键技能覆盖不足")

        person_min = person["expected_salary_min"]
        person_max = person["expected_salary_max"]
        salary_overlap = max(
            0, min(person_max, job["salary_max"]) - max(person_min, job["salary_min"])
        )
        salary_span = max(person_max, job["salary_max"]) - min(person_min, job["salary_min"])
        salary_ratio = salary_overlap / salary_span if salary_span else 1.0
        factors["薪资交集"] = salary_ratio
        if person_min > job["salary_max"]:
            conflicts.append("期望薪资高于岗位上限")

        region_ratio = 1.0 if person["preferred_region"] == job["region"] else 0.35
        factors["地区匹配"] = region_ratio
        if region_ratio < 1:
            conflicts.append("期望地区与岗位地区不同")

        education_ratio = (
            1.0
            if EDUCATION_SCORE.get(person["education"], -1)
            >= EDUCATION_SCORE.get(job["education_min"], 0)
            else 0.2
        )
        factors["学历要求"] = education_ratio
        if education_ratio < 1:
            conflicts.append("学历低于岗位建议")

        experience_ratio = min(1.0, person["years_experience"] / max(job["experience_min"], 0.5))
        factors["经验要求"] = experience_ratio
        if experience_ratio < 1:
            conflicts.append("相关经验低于岗位建议")

        shift_ratio = (
            1.0
            if job["shift"] == "不限"
            or person["available_shift"] == "不限"
            or person["available_shift"] == job["shift"]
            else 0.25
        )
        factors["班次适配"] = shift_ratio
        if shift_ratio < 1:
            conflicts.append("班次偏好存在冲突")

        preferred_industries = set(
            person.get("canonical_industries") or person["preferred_industries"]
        )
        industry = job.get("industry_id") or job["industry"]
        industry_ratio = 1.0 if industry in preferred_industries else 0.4
        factors["行业偏好"] = industry_ratio

        weighted = (
            0.38 * skill_ratio
            + 0.16 * salary_ratio
            + 0.14 * region_ratio
            + 0.10 * education_ratio
            + 0.10 * experience_ratio
            + 0.07 * shift_ratio
            + 0.05 * industry_ratio
        )
        return {
            "eligible": True,
            "rule_score": round(weighted * 100, 2),
            "factors": factors,
            "conflicts": conflicts,
        }


class ExplanationService:
    LABELS = {
        "技能匹配": "岗位关键技能覆盖",
        "薪资交集": "薪资区间有交集",
        "地区匹配": "期望地区匹配",
        "学历要求": "学历满足要求",
        "经验要求": "经验满足建议",
        "班次适配": "班次偏好适配",
        "行业偏好": "行业偏好相符",
    }

    def build(
        self,
        evaluation: dict[str, Any],
        semantic_score: float,
        local_semantic_score: float,
        llm_assessment: CandidateSemanticAssessment | None = None,
        provider: str = "",
        model: str = "",
    ) -> dict[str, Any]:
        rule_positives = [
            self.LABELS[key] for key, value in evaluation["factors"].items() if value >= 0.75
        ]
        if llm_assessment:
            positives = list(llm_assessment.positives) + rule_positives
            conflicts = list(evaluation["conflicts"]) + list(llm_assessment.risks)
            summary = llm_assessment.summary
            review_questions = list(llm_assessment.review_questions)
        else:
            positives = rule_positives
            conflicts = list(evaluation["conflicts"])
            summary = "当前未配置大模型，结果仅使用规则与本地文本相似度基线。"
            review_questions = []
            if semantic_score >= 70:
                positives.append("技能与岗位文本相似度较高")
        positives = list(dict.fromkeys(positives))
        conflicts = list(dict.fromkeys(conflicts))
        return {
            "positives": positives[:4],
            "conflicts": conflicts[:4],
            "factor_scores": {
                key: round(value * 100, 1) for key, value in evaluation["factors"].items()
            },
            "summary": summary,
            "review_questions": review_questions[:3],
            "human_review_required": bool(conflicts)
            or bool(review_questions)
            or semantic_score < 55,
            "provenance": {
                "llm_used": bool(llm_assessment),
                "provider": provider if llm_assessment else None,
                "model": model if llm_assessment else None,
                "semantic_score": semantic_score,
                "local_similarity": local_semantic_score,
            },
        }


class SemanticRankerService:
    def __init__(self, context: AppContext) -> None:
        self.context = context

    @staticmethod
    def _semantic(job: dict[str, Any], person: dict[str, Any]) -> float:
        left = " ".join(job["required_skills"] + [job["job_title"], job["industry"]])
        right = " ".join(
            person["skills"] + [person.get("major", "")] + person["preferred_industries"]
        )
        if fuzz is not None:
            return round(float(fuzz.WRatio(left, right)), 2)
        return round(SequenceMatcher(None, left, right).ratio() * 100, 2)

    def rank(self, batch_id: str, job_id: str, top_n: int, actor: str) -> list[dict[str, Any]]:
        job = self.context.db.get_job(batch_id, job_id)
        if not job:
            raise ValueError("岗位不存在或批次无效")
        rules: RuleFilterService = self.context.services.get("match.rules")
        explainer: ExplanationService = self.context.services.get("match.explain")
        llm: OpenAICompatibleLlmService = self.context.services.get("llm.rerank")
        candidates: list[dict[str, Any]] = []
        for person in self.context.db.get_people(batch_id):
            evaluation = rules.evaluate(job, person)
            if not evaluation["eligible"]:
                continue
            local_semantic_score = self._semantic(job, person)
            candidates.append(
                {
                    "person": person,
                    "evaluation": evaluation,
                    "local_semantic_score": local_semantic_score,
                    "baseline_score": round(
                        0.75 * evaluation["rule_score"] + 0.25 * local_semantic_score,
                        2,
                    ),
                }
            )
        candidates.sort(key=lambda item: (-item["baseline_score"], item["person"]["person_id"]))
        target_count = max(1, min(top_n, 50))
        shortlist_count = min(
            len(candidates),
            max(target_count, self.context.settings.llm_candidate_limit),
        )
        shortlist = candidates[:shortlist_count]

        if self.context.settings.llm_required and not llm.configured:
            raise ValueError("大模型被设为必需，但 LLM_API_KEY 尚未配置")
        llm_result = None
        if llm.configured and shortlist:
            try:
                llm_result = llm.rerank(job, shortlist)
            except LlmProviderError as exc:
                raise ValueError(str(exc)) from exc

        ranked: list[dict[str, Any]] = []
        for candidate in shortlist:
            person = candidate["person"]
            evaluation = candidate["evaluation"]
            assessment = (
                llm_result.assessments[person["person_id"]] if llm_result is not None else None
            )
            semantic_score = (
                assessment.score if assessment is not None else candidate["local_semantic_score"]
            )
            if assessment is not None:
                final_score = (1 - self.context.settings.llm_weight) * evaluation[
                    "rule_score"
                ] + self.context.settings.llm_weight * semantic_score
                model_version = (
                    f"{LLM_MODEL_VERSION}:{self.context.settings.llm_provider}/"
                    f"{self.context.settings.llm_model}"
                )
            else:
                final_score = candidate["baseline_score"]
                model_version = BASELINE_MODEL_VERSION
            ranked.append(
                {
                    "match_id": str(uuid.uuid4()),
                    "person_id": person["person_id"],
                    "score": round(final_score, 2),
                    "rule_score": evaluation["rule_score"],
                    "semantic_score": semantic_score,
                    "explanation": explainer.build(
                        evaluation,
                        semantic_score,
                        candidate["local_semantic_score"],
                        llm_assessment=assessment,
                        provider=self.context.settings.llm_provider,
                        model=self.context.settings.llm_model,
                    ),
                    "model_version": model_version,
                }
            )

        ranked.sort(key=lambda item: (-item["score"], item["person_id"]))
        selected = ranked[:target_count]
        for index, item in enumerate(selected, start=1):
            item["rank"] = index
        self.context.db.save_matches(batch_id, job_id, selected)
        self.context.events.publish(
            "match.ranked",
            {
                "batch_id": batch_id,
                "job_id": job_id,
                "count": len(selected),
                "llm_used": llm_result is not None,
            },
        )
        audit_details: dict[str, object] = {
            "batch_id": batch_id,
            "job_id": job_id,
            "top_n": len(selected),
            "shortlist_count": shortlist_count,
            "llm_used": llm_result is not None,
            "provider": self.context.settings.llm_provider,
            "model": self.context.settings.llm_model,
            "model_version": selected[0]["model_version"] if selected else BASELINE_MODEL_VERSION,
        }
        if llm_result is not None:
            audit_details["llm_response_id"] = llm_result.response_id
            audit_details["llm_usage"] = llm_result.usage
        self.context.audit(
            "match.ranked",
            actor,
            audit_details,
        )
        return self.context.db.list_matches(batch_id, job_id)


class RuleFilterPlugin(Plugin):
    manifest = PluginManifest(
        id="rule-filter",
        version="1.0.0",
        name="硬规则评分",
        description="对就业状态、技能、薪资、地区、学历、经验和班次进行可解释评分",
        provides=("match.rules",),
        permissions=("snapshot:read",),
        cleanup_strategy="remove stateless rule service; existing match evidence remains versioned",
    )

    def install(self, context: AppContext) -> None:
        context.services.register("match.rules", self.manifest.id, RuleFilterService())


class ExplanationPlugin(Plugin):
    manifest = PluginManifest(
        id="match-explanation",
        version="1.0.0",
        name="推荐解释",
        description="把评分因子转为正向理由、冲突和人工复核提示",
        provides=("match.explain",),
        requires=("match.rules",),
        permissions=("match:read",),
        cleanup_strategy="remove stateless explanation service; preserve generated explanations",
    )

    def install(self, context: AppContext) -> None:
        context.services.register("match.explain", self.manifest.id, ExplanationService())


class SemanticRankerPlugin(Plugin):
    manifest = PluginManifest(
        id="semantic-ranker",
        version="2.0.0",
        name="规则召回 + LLM复排",
        description="规则先形成可审计候选池，再由可配置大模型做语义复排与解释",
        provides=("match.rank",),
        requires=("match.rules", "match.explain", "llm.rerank"),
        permissions=("snapshot:read", "match:write", "llm:invoke"),
        events_out=("match.ranked",),
        cleanup_strategy=(
            "remove rank service; soft-retire prior results only when a new run is saved"
        ),
    )

    def install(self, context: AppContext) -> None:
        context.services.register("match.rank", self.manifest.id, SemanticRankerService(context))
