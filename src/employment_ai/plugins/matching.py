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

EDUCATION_SCORE = {name: index for index, name in enumerate(EDUCATION_LEVELS)}
ELIGIBLE_STATUSES = {"求职中", "失业", "灵活就业"}
MODEL_VERSION = "hybrid-rule-semantic-v1.0"


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

    def build(self, evaluation: dict[str, Any], semantic_score: float) -> dict[str, Any]:
        positives = [
            self.LABELS[key] for key, value in evaluation["factors"].items() if value >= 0.75
        ]
        if semantic_score >= 70:
            positives.append("技能与岗位描述语义接近")
        return {
            "positives": positives[:4],
            "conflicts": evaluation["conflicts"][:4],
            "factor_scores": {
                key: round(value * 100, 1) for key, value in evaluation["factors"].items()
            },
            "human_review_required": bool(evaluation["conflicts"]) or semantic_score < 55,
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
        candidates: list[dict[str, Any]] = []
        for person in self.context.db.get_people(batch_id):
            evaluation = rules.evaluate(job, person)
            if not evaluation["eligible"]:
                continue
            semantic_score = self._semantic(job, person)
            final_score = 0.75 * evaluation["rule_score"] + 0.25 * semantic_score
            candidates.append(
                {
                    "match_id": str(uuid.uuid4()),
                    "person_id": person["person_id"],
                    "score": round(final_score, 2),
                    "rule_score": evaluation["rule_score"],
                    "semantic_score": semantic_score,
                    "explanation": explainer.build(evaluation, semantic_score),
                    "model_version": MODEL_VERSION,
                }
            )
        candidates.sort(key=lambda item: (-item["score"], item["person_id"]))
        selected = candidates[: max(1, min(top_n, 50))]
        for index, item in enumerate(selected, start=1):
            item["rank"] = index
        self.context.db.save_matches(batch_id, job_id, selected)
        self.context.events.publish(
            "match.ranked",
            {"batch_id": batch_id, "job_id": job_id, "count": len(selected)},
        )
        self.context.audit(
            "match.ranked",
            actor,
            {
                "batch_id": batch_id,
                "job_id": job_id,
                "top_n": len(selected),
                "model_version": MODEL_VERSION,
            },
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
        version="1.0.0",
        name="规则+语义排序",
        description="使用规则基线与本地轻量语义相似度生成Top-N，不调用外部模型",
        provides=("match.rank",),
        requires=("match.rules", "match.explain"),
        permissions=("snapshot:read", "match:write"),
        events_out=("match.ranked",),
        cleanup_strategy=(
            "remove rank service; soft-retire prior results only when a new run is saved"
        ),
    )

    def install(self, context: AppContext) -> None:
        context.services.register("match.rank", self.manifest.id, SemanticRankerService(context))
