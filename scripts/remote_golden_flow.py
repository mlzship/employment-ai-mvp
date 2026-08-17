from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

BASE_URL = os.getenv("MVP_BASE_URL", "http://127.0.0.1:18080")


def request_json(path: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main() -> None:
    health = request_json("/healthz")
    batches = request_json("/api/batches")
    if not batches:
        raise RuntimeError("auto-seed batch is missing")
    batch = batches[0]
    batch_id = batch["batch_id"]
    jobs = request_json(f"/api/jobs?batch_id={batch_id}")
    job = next(item for item in jobs if item["job_id"] == "J001")
    matches = request_json(
        "/api/matches/run",
        {"batch_id": batch_id, "job_id": job["job_id"], "top_n": 10},
    )
    first = matches[0]
    review = request_json(
        "/api/reviews",
        {"match_id": first["match_id"], "decision": "accepted", "reason": ""},
    )
    feedback = request_json(
        "/api/feedback",
        {"match_id": first["match_id"], "outcome": "effective", "reason": "remote-smoke"},
    )
    metrics = request_json(f"/api/metrics?batch_id={batch_id}")
    with urllib.request.urlopen(
        f"{BASE_URL}/api/export?batch_id={batch_id}&job_id={job['job_id']}", timeout=20
    ) as response:
        exported = response.read()

    result = {
        "health": health["status"],
        "enabled_plugins": sum(1 for plugin in health["plugins"] if plugin["state"] == "enabled"),
        "batch": {
            "status": batch["status"],
            "people": batch["person_count"],
            "jobs": batch["job_count"],
        },
        "ontology": {
            "occupation_id": job["occupation_id"],
            "canonical_skill": job["canonical_required_skills"][0],
            "version": job["semantic_evidence"]["ontology_version"],
        },
        "top10": {
            "count": len(matches),
            "first_person_id": first["person_id"],
            "first_score": first["score"],
            "has_explanation": bool(first["explanation"]["positives"]),
        },
        "review_id": review["review_id"],
        "feedback_id": feedback["feedback_id"],
        "metrics": metrics,
        "csv_bytes": len(exported),
        "csv_has_bom": exported.startswith(b"\xef\xbb\xbf"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
