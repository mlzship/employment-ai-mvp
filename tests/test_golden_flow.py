from pathlib import Path

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
