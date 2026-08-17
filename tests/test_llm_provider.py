import json

import httpx
import pytest

from employment_ai.plugins.llm_provider import LlmProviderError, OpenAICompatibleLlmService
from employment_ai.settings import Settings


def _job() -> dict:
    return {
        "job_id": "J001",
        "job_title": "数控操作员",
        "employer_name": "虚构制造企业",
        "industry": "机械制造",
        "region": "赣江新区",
        "salary_min": 6000,
        "salary_max": 9000,
        "education_min": "中专",
        "experience_min": 1,
        "required_skills": ["CNC操作", "机械识图"],
        "canonical_required_skills": ["skill:cnc_operation", "skill:technical_drawing"],
        "shift": "白班",
    }


def _candidates() -> list[dict]:
    return [
        {
            "person": {
                "person_id": person_id,
                "education": "大专",
                "major": "机械制造",
                "skills": ["CNC操作"],
                "canonical_skills": ["skill:cnc_operation"],
                "employment_status": "求职中",
                "expected_salary_min": 6000,
                "expected_salary_max": 8500,
                "preferred_region": "赣江新区",
                "preferred_industries": ["机械制造"],
                "years_experience": 2,
                "available_shift": "白班",
            },
            "evaluation": {
                "rule_score": rule_score,
                "factors": {"技能匹配": 0.8},
                "conflicts": [],
            },
            "local_semantic_score": 70.0,
        }
        for person_id, rule_score in (("P001", 82.0), ("P002", 78.0))
    ]


def test_openai_compatible_provider_returns_validated_assessments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer secret-for-test"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "rankings": [
                                        {
                                            "person_id": "P001",
                                            "semantic_score": 88,
                                            "summary": "技能与岗位职责高度相关",
                                            "positives": ["数控技能直接相关"],
                                            "risks": [],
                                            "review_questions": ["是否熟悉目标设备型号？"],
                                        },
                                        {
                                            "person_id": "P002",
                                            "semantic_score": 72,
                                            "summary": "基础相关，仍需核验",
                                            "positives": ["专业方向相关"],
                                            "risks": ["设备经验未明确"],
                                            "review_questions": [],
                                        },
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 300, "completion_tokens": 120, "total_tokens": 420},
            },
        )

    settings = Settings(llm_api_key="secret-for-test")
    service = OpenAICompatibleLlmService(settings, httpx.MockTransport(handler))

    result = service.rerank(_job(), _candidates())

    assert result.assessments["P001"].score == 88
    assert result.assessments["P002"].risks == ("设备经验未明确",)
    assert result.usage["total_tokens"] == 420
    assert "secret-for-test" not in json.dumps(service.status())


def test_provider_rejects_incomplete_candidate_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"rankings":[{"person_id":"P001","semantic_score":80}]}'
                        }
                    }
                ]
            },
        )

    service = OpenAICompatibleLlmService(
        Settings(llm_api_key="secret-for-test"),
        httpx.MockTransport(handler),
    )

    with pytest.raises(LlmProviderError, match="完整"):
        service.rerank(_job(), _candidates())


def test_unconfigured_provider_reports_baseline_without_exposing_secret() -> None:
    status = OpenAICompatibleLlmService(Settings()).status()

    assert status["configured"] is False
    assert status["mode"] == "baseline"
    assert "api_key" not in status
