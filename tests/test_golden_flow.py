import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from employment_ai.main import create_app
from employment_ai.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_full_golden_flow_and_semantic_persistence(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        database_path=tmp_path / "golden-flow.db",
        seed_xlsx=ROOT / "data/synthetic/employment_ai_demo.xlsx",
        ontology_path=ROOT / "data/ontology/employment_ontology.json",
        auto_seed=True,
        auth_disabled=True,
        session_secret="test-session-secret-with-enough-length",
    )

    with TestClient(create_app(settings)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        llm_status = client.get("/api/llm/status").json()
        assert llm_status["configured"] is False
        assert llm_status["mode"] == "baseline"

        batches = client.get("/api/batches").json()
        assert len(batches) == 1
        batch = batches[0]
        assert batch["status"] == "ready"
        assert batch["person_count"] == 1000
        assert batch["job_count"] == 12

        jobs = client.get("/api/jobs", params={"batch_id": batch["batch_id"]}).json()
        cnc_job = next(job for job in jobs if job["job_id"] == "J001")
        assert cnc_job["occupation_id"] == "occupation:cnc_operator"
        assert "skill:cnc_operation" in cnc_job["canonical_required_skills"]

        people = client.app.state.context.db.get_people(batch["batch_id"])
        assert people[0]["skills"][0] == "CNC操作"
        assert people[0]["canonical_skills"][0] == "skill:cnc_operation"
        assert people[0]["semantic_evidence"]["ontology_version"] == "1.0.0"

        response = client.post(
            "/api/matches/run",
            json={"batch_id": batch["batch_id"], "job_id": "J001", "top_n": 10},
        )
        assert response.status_code == 200
        matches = response.json()
        assert len(matches) == 10
        assert [item["score"] for item in matches] == sorted(
            [item["score"] for item in matches], reverse=True
        )
        assert matches[0]["explanation"]["positives"]
        assert matches[0]["explanation"]["provenance"]["llm_used"] is False
        assert "未配置大模型" in matches[0]["explanation"]["summary"]

        match_id = matches[0]["match_id"]
        review = client.post(
            "/api/reviews",
            json={"match_id": match_id, "decision": "accepted", "reason": ""},
        )
        assert review.status_code == 200

        feedback = client.post(
            "/api/feedback",
            json={"match_id": match_id, "outcome": "effective", "reason": "演示反馈"},
        )
        assert feedback.status_code == 200

        metrics = client.get("/api/metrics", params={"batch_id": batch["batch_id"]}).json()
        assert metrics["matches"] == 10
        assert metrics["reviewed"] == 1
        assert metrics["feedback_count"] == 1
        assert metrics["acceptance_rate"] == 1.0

        exported = client.get(
            "/api/export", params={"batch_id": batch["batch_id"], "job_id": "J001"}
        )
        assert exported.status_code == 200
        assert exported.content.startswith(b"\xef\xbb\xbf")
        assert b"person_id" in exported.content


def test_invalid_xlsx_container_is_rejected(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        database_path=tmp_path / "invalid-upload.db",
        seed_xlsx=ROOT / "data/synthetic/employment_ai_demo.xlsx",
        ontology_path=ROOT / "data/ontology/employment_ontology.json",
        auto_seed=False,
        auth_disabled=True,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/import",
            files={
                "file": (
                    "invalid.xlsx",
                    b"PK-not-a-real-xlsx-container",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert response.status_code == 400
    assert "有效" in response.json()["detail"]


def test_production_rejects_demo_credentials(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        database_path=tmp_path / "production.db",
        ontology_path=ROOT / "data/ontology/employment_ontology.json",
        auto_seed=False,
    )

    with pytest.raises(ValueError, match="SESSION_SECRET"):
        with TestClient(create_app(settings)):
            pass


def test_static_assets_use_https_safe_relative_paths(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        database_path=tmp_path / "static-assets.db",
        ontology_path=ROOT / "data/ontology/employment_ontology.json",
        auto_seed=False,
        auth_disabled=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert 'href="/static/styles.css"' in response.text
    assert "http://testserver/static" not in response.text


def test_matching_uses_configured_llm_reranker(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        database_path=tmp_path / "llm-flow.db",
        seed_xlsx=ROOT / "data/synthetic/employment_ai_demo.xlsx",
        ontology_path=ROOT / "data/ontology/employment_ontology.json",
        auto_seed=True,
        auth_disabled=True,
        llm_api_key="llm-test-secret",
        llm_candidate_limit=10,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        evidence = json.loads(payload["messages"][1]["content"].split("\n", 1)[1])
        rankings = [
            {
                "person_id": item["person_id"],
                "semantic_score": 95 - index,
                "summary": "大模型已根据技能迁移性完成复排",
                "positives": ["相关技能可迁移"],
                "risks": item["rule_conflicts"],
                "review_questions": ["请人工核验实际项目经验"],
            }
            for index, item in enumerate(evidence["candidates"])
        ]
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-integration",
                "choices": [{"message": {"content": json.dumps({"rankings": rankings})}}],
                "usage": {"total_tokens": 800},
            },
        )

    with TestClient(create_app(settings)) as client:
        provider = client.app.state.context.services.get("llm.rerank")
        provider.transport = httpx.MockTransport(handler)
        batch_id = client.get("/api/batches").json()[0]["batch_id"]
        response = client.post(
            "/api/matches/run",
            json={"batch_id": batch_id, "job_id": "J001", "top_n": 5},
        )

    assert response.status_code == 200
    matches = response.json()
    assert len(matches) == 5
    assert all(item["explanation"]["provenance"]["llm_used"] for item in matches)
    assert all(item["explanation"]["provenance"]["provider"] == "deepseek" for item in matches)
    assert all(item["model_version"].startswith("hybrid-rule-llm-v2.0") for item in matches)
