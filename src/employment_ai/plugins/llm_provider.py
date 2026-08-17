from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from employment_ai.core.context import AppContext
from employment_ai.core.contracts import Plugin, PluginManifest
from employment_ai.settings import Settings


class LlmProviderError(RuntimeError):
    """A safe-to-display provider or response validation error."""


@dataclass(frozen=True, slots=True)
class CandidateSemanticAssessment:
    person_id: str
    score: float
    summary: str
    positives: tuple[str, ...]
    risks: tuple[str, ...]
    review_questions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LlmRerankResult:
    assessments: dict[str, CandidateSemanticAssessment]
    response_id: str
    usage: dict[str, int]


class OpenAICompatibleLlmService:
    """Provider/model-routed JSON reranking over an OpenAI-compatible endpoint."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.settings.llm_api_key)

    @property
    def endpoint(self) -> str:
        base_url = self.settings.llm_base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.settings.llm_provider,
            "model": self.settings.llm_model,
            "configured": self.configured,
            "mode": "llm" if self.configured else "baseline",
            "base_url": self.settings.llm_base_url,
            "candidate_limit": self.settings.llm_candidate_limit,
            "weight": self.settings.llm_weight,
            "required": self.settings.llm_required,
            "thinking": self.settings.llm_thinking,
        }

    @staticmethod
    def _candidate_payload(candidate: dict[str, Any]) -> dict[str, Any]:
        person = candidate["person"]
        evaluation = candidate["evaluation"]
        return {
            "person_id": person["person_id"],
            "education": person["education"],
            "major": person.get("major", ""),
            "skills": person.get("skills", []),
            "canonical_skills": person.get("canonical_skills", []),
            "employment_status": person["employment_status"],
            "expected_salary": [
                person["expected_salary_min"],
                person["expected_salary_max"],
            ],
            "preferred_region": person["preferred_region"],
            "preferred_industries": person.get("preferred_industries", []),
            "years_experience": person["years_experience"],
            "available_shift": person["available_shift"],
            "rule_score": evaluation["rule_score"],
            "rule_factors": evaluation["factors"],
            "rule_conflicts": evaluation["conflicts"],
            "local_similarity": candidate["local_semantic_score"],
        }

    @staticmethod
    def _job_payload(job: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": job["job_id"],
            "title": job["job_title"],
            "employer": job["employer_name"],
            "industry": job["industry"],
            "region": job["region"],
            "salary": [job["salary_min"], job["salary_max"]],
            "education_min": job["education_min"],
            "experience_min": job["experience_min"],
            "required_skills": job["required_skills"],
            "canonical_required_skills": job.get("canonical_required_skills", []),
            "shift": job["shift"],
        }

    def _request_payload(
        self, job: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        system_prompt = """
你是公共就业服务场景的人岗语义复核模型。硬规则负责资格与明确冲突，你不能覆盖或删除硬规则冲突。
你的任务是理解技能迁移性、专业与岗位职责的相关性、经验可迁移性，并指出需要人工核实的问题。
禁止根据姓名、性别、年龄、民族、健康、残障或其他敏感属性推断；输入中也不会提供这些字段。
只依据输入证据，对每个候选人恰好输出一次。输出必须是合法 JSON，不要输出 Markdown 或额外文字。
JSON 格式示例：
{"rankings":[{"person_id":"P001","semantic_score":82,"summary":"技能可迁移但需核验设备经验","positives":["具备相关工艺技能"],"risks":["设备型号经验未明确"],"review_questions":["是否操作过同类设备？"]}]}
""".strip()
        evidence = {
            "job": self._job_payload(job),
            "candidates": [self._candidate_payload(item) for item in candidates],
        }
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "请基于以下证据完成全部候选人的 JSON 语义复排：\n"
                    + json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": 5000,
        }
        if self.settings.llm_provider == "deepseek":
            payload["thinking"] = {"type": "enabled" if self.settings.llm_thinking else "disabled"}
        return payload

    @staticmethod
    def _text(value: Any, limit: int) -> str:
        return " ".join(str(value or "").strip().split())[:limit]

    @classmethod
    def _text_list(cls, value: Any, limit: int) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(text for item in value[:limit] if (text := cls._text(item, 160)))

    @classmethod
    def _parse_result(
        cls,
        response_payload: dict[str, Any],
        expected_ids: set[str],
    ) -> LlmRerankResult:
        try:
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmProviderError("大模型响应缺少 choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise LlmProviderError("大模型返回了空内容")
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        try:
            document = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LlmProviderError("大模型未返回合法 JSON") from exc
        rankings = document.get("rankings") if isinstance(document, dict) else None
        if not isinstance(rankings, list):
            raise LlmProviderError("大模型 JSON 缺少 rankings 数组")

        assessments: dict[str, CandidateSemanticAssessment] = {}
        for item in rankings:
            if not isinstance(item, dict):
                raise LlmProviderError("大模型 rankings 包含非对象条目")
            person_id = cls._text(item.get("person_id"), 80)
            if person_id not in expected_ids or person_id in assessments:
                raise LlmProviderError("大模型返回了未知或重复的候选人 ID")
            try:
                score = float(item["semantic_score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise LlmProviderError(f"候选人 {person_id} 缺少有效语义分") from exc
            if not 0 <= score <= 100:
                raise LlmProviderError(f"候选人 {person_id} 的语义分超出 0-100")
            assessments[person_id] = CandidateSemanticAssessment(
                person_id=person_id,
                score=round(score, 2),
                summary=cls._text(item.get("summary"), 240),
                positives=cls._text_list(item.get("positives"), 4),
                risks=cls._text_list(item.get("risks"), 4),
                review_questions=cls._text_list(item.get("review_questions"), 3),
            )
        if set(assessments) != expected_ids:
            raise LlmProviderError("大模型没有完整返回全部候选人的评估")

        raw_usage = response_payload.get("usage")
        usage = {
            key: int(value)
            for key, value in (raw_usage.items() if isinstance(raw_usage, dict) else [])
            if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
            and isinstance(value, int)
        }
        return LlmRerankResult(
            assessments=assessments,
            response_id=cls._text(response_payload.get("id"), 120),
            usage=usage,
        )

    def rerank(self, job: dict[str, Any], candidates: list[dict[str, Any]]) -> LlmRerankResult:
        if not self.configured:
            raise LlmProviderError("大模型未配置：请设置 LLM_API_KEY")
        expected_ids = {item["person"]["person_id"] for item in candidates}
        if not expected_ids:
            raise LlmProviderError("没有可供大模型复排的候选人")
        try:
            with httpx.Client(
                timeout=self.settings.llm_timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=self._request_payload(job, candidates),
                )
        except httpx.TimeoutException as exc:
            raise LlmProviderError("大模型请求超时，请稍后重试") from exc
        except httpx.RequestError as exc:
            raise LlmProviderError("无法连接大模型服务，请检查地址和网络") from exc
        if not 200 <= response.status_code < 300:
            raise LlmProviderError(f"大模型服务返回 HTTP {response.status_code}")
        try:
            response_payload = response.json()
        except ValueError as exc:
            raise LlmProviderError("大模型服务未返回 JSON 响应") from exc
        if not isinstance(response_payload, dict):
            raise LlmProviderError("大模型服务响应结构无效")
        return self._parse_result(response_payload, expected_ids)


class LlmProviderPlugin(Plugin):
    manifest = PluginManifest(
        id="llm-provider",
        version="1.0.0",
        name="大模型提供方",
        description="按 provider/model 路由 DeepSeek 或 OpenAI 兼容接口，密钥仅从环境变量读取",
        provides=("llm.rerank",),
        permissions=("network:llm",),
        config_schema={
            "provider": "LLM_PROVIDER",
            "model": "LLM_MODEL",
            "base_url": "LLM_BASE_URL",
            "api_key": "LLM_API_KEY (write-only environment secret)",
        },
        cleanup_strategy="remove provider adapter; saved matching evidence remains versioned",
    )

    def install(self, context: AppContext) -> None:
        context.services.register(
            "llm.rerank",
            self.manifest.id,
            OpenAICompatibleLlmService(context.settings),
        )

    def health(self, context: AppContext) -> dict[str, Any]:
        service: OpenAICompatibleLlmService = context.services.get("llm.rerank")
        return {"status": "ok" if service.configured else "degraded"}
