from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL DEFAULT 'demo',
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    person_count INTEGER NOT NULL DEFAULT 0,
                    job_count INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS persons (
                    batch_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'demo',
                    education TEXT NOT NULL,
                    major TEXT,
                    skill_level TEXT,
                    skills_json TEXT NOT NULL,
                    canonical_skills_json TEXT NOT NULL DEFAULT '[]',
                    employment_status TEXT NOT NULL,
                    expected_salary_min INTEGER NOT NULL,
                    expected_salary_max INTEGER NOT NULL,
                    preferred_region TEXT NOT NULL,
                    preferred_industries_json TEXT NOT NULL,
                    canonical_industries_json TEXT NOT NULL DEFAULT '[]',
                    special_tags_json TEXT NOT NULL,
                    semantic_evidence_json TEXT NOT NULL DEFAULT '{}',
                    town TEXT NOT NULL,
                    village TEXT,
                    years_experience REAL NOT NULL,
                    available_shift TEXT NOT NULL,
                    source_updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (batch_id, person_id),
                    FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    batch_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'demo',
                    employer_name TEXT NOT NULL,
                    job_title TEXT NOT NULL,
                    region TEXT NOT NULL,
                    salary_min INTEGER NOT NULL,
                    salary_max INTEGER NOT NULL,
                    education_min TEXT NOT NULL,
                    experience_min REAL NOT NULL,
                    required_skills_json TEXT NOT NULL,
                    canonical_required_skills_json TEXT NOT NULL DEFAULT '[]',
                    industry TEXT NOT NULL,
                    occupation_id TEXT NOT NULL DEFAULT '',
                    industry_id TEXT NOT NULL DEFAULT '',
                    semantic_evidence_json TEXT NOT NULL DEFAULT '{}',
                    shift TEXT NOT NULL,
                    headcount INTEGER NOT NULL,
                    valid_until TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (batch_id, job_id),
                    FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
                );

                CREATE TABLE IF NOT EXISTS matches (
                    match_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'demo',
                    rank_no INTEGER NOT NULL,
                    score REAL NOT NULL,
                    rule_score REAL NOT NULL,
                    semantic_score REAL NOT NULL,
                    explanation_json TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (batch_id, job_id) REFERENCES jobs(batch_id, job_id),
                    FOREIGN KEY (batch_id, person_id) REFERENCES persons(batch_id, person_id)
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    match_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'demo',
                    decision TEXT NOT NULL,
                    reason TEXT,
                    operator TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (match_id) REFERENCES matches(match_id)
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    match_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'demo',
                    outcome TEXT NOT NULL,
                    reason TEXT,
                    operator TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (match_id) REFERENCES matches(match_id)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    audit_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL DEFAULT 'demo',
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_matches_batch_job
                    ON matches(batch_id, job_id, deleted, rank_no);
                CREATE INDEX IF NOT EXISTS idx_reviews_match
                    ON reviews(match_id, deleted, created_at);
                CREATE INDEX IF NOT EXISTS idx_feedback_match
                    ON feedback(match_id, deleted, created_at);
                """
            )
            self._ensure_column(
                db, "persons", "canonical_skills_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(
                db, "persons", "canonical_industries_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(
                db, "persons", "semantic_evidence_json", "TEXT NOT NULL DEFAULT '{}'"
            )
            self._ensure_column(
                db, "jobs", "canonical_required_skills_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(db, "jobs", "occupation_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "jobs", "industry_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "jobs", "semantic_evidence_json", "TEXT NOT NULL DEFAULT '{}'")

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def add_audit(self, action: str, actor: str, details: dict[str, object]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit_logs(audit_id, action, actor, details_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), action, actor, json.dumps(details, ensure_ascii=False), _now()),
            )

    def batch_count(self) -> int:
        with self.connect() as db:
            row = db.execute("SELECT COUNT(*) AS total FROM batches WHERE deleted=0").fetchone()
        return int(row["total"])

    def create_batch(
        self,
        filename: str,
        status: str,
        person_count: int,
        job_count: int,
        errors: list[dict[str, Any]],
    ) -> str:
        batch_id = f"B{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6]}"
        now = _now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO batches(
                    batch_id, filename, status, person_count, job_count, errors_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id,
                    filename,
                    status,
                    person_count,
                    job_count,
                    json.dumps(errors, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return batch_id

    def store_snapshot(
        self, batch_id: str, people: list[dict[str, Any]], jobs: list[dict[str, Any]]
    ) -> None:
        now = _now()
        with self.connect() as db:
            db.executemany(
                """INSERT INTO persons(
                    batch_id, person_id, education, major, skill_level, skills_json,
                    canonical_skills_json,
                    employment_status, expected_salary_min, expected_salary_max,
                    preferred_region, preferred_industries_json,
                    canonical_industries_json, special_tags_json, semantic_evidence_json,
                    town, village, years_experience, available_shift, source_updated_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        batch_id,
                        item["person_id"],
                        item["education"],
                        item.get("major", ""),
                        item.get("skill_level", "无"),
                        json.dumps(item["skills"], ensure_ascii=False),
                        json.dumps(item.get("canonical_skills", []), ensure_ascii=False),
                        item["employment_status"],
                        item["expected_salary_min"],
                        item["expected_salary_max"],
                        item["preferred_region"],
                        json.dumps(item.get("preferred_industries", []), ensure_ascii=False),
                        json.dumps(item.get("canonical_industries", []), ensure_ascii=False),
                        json.dumps(item.get("special_tags", []), ensure_ascii=False),
                        json.dumps(item.get("semantic_evidence", {}), ensure_ascii=False),
                        item["town"],
                        item.get("village", ""),
                        item["years_experience"],
                        item["available_shift"],
                        item["source_updated_at"],
                        now,
                        now,
                    )
                    for item in people
                ],
            )
            db.executemany(
                """INSERT INTO jobs(
                    batch_id, job_id, employer_name, job_title, region, salary_min,
                    salary_max, education_min, experience_min, required_skills_json,
                    canonical_required_skills_json, industry, occupation_id, industry_id,
                    semantic_evidence_json, shift, headcount, valid_until, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        batch_id,
                        item["job_id"],
                        item["employer_name"],
                        item["job_title"],
                        item["region"],
                        item["salary_min"],
                        item["salary_max"],
                        item["education_min"],
                        item["experience_min"],
                        json.dumps(item["required_skills"], ensure_ascii=False),
                        json.dumps(item.get("canonical_required_skills", []), ensure_ascii=False),
                        item["industry"],
                        item.get("occupation_id", ""),
                        item.get("industry_id", ""),
                        json.dumps(item.get("semantic_evidence", {}), ensure_ascii=False),
                        item["shift"],
                        item["headcount"],
                        item["valid_until"],
                        item["status"],
                        now,
                        now,
                    )
                    for item in jobs
                ],
            )

    @staticmethod
    def _decode(row: sqlite3.Row, json_fields: tuple[str, ...]) -> dict[str, Any]:
        result = dict(row)
        for field in json_fields:
            result[field.removesuffix("_json")] = json.loads(result.pop(field) or "[]")
        return result

    def list_batches(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM batches WHERE deleted=0 ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["errors"] = json.loads(item.pop("errors_json") or "[]")
            result.append(item)
        return result

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM batches WHERE batch_id=? AND deleted=0", (batch_id,)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["errors"] = json.loads(item.pop("errors_json") or "[]")
        return item

    def get_people(self, batch_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM persons WHERE batch_id=? AND deleted=0 ORDER BY person_id",
                (batch_id,),
            ).fetchall()
        return [
            self._decode(
                row,
                (
                    "skills_json",
                    "canonical_skills_json",
                    "preferred_industries_json",
                    "canonical_industries_json",
                    "special_tags_json",
                    "semantic_evidence_json",
                ),
            )
            for row in rows
        ]

    def get_jobs(self, batch_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE batch_id=? AND deleted=0 ORDER BY job_id",
                (batch_id,),
            ).fetchall()
        return [
            self._decode(
                row,
                (
                    "required_skills_json",
                    "canonical_required_skills_json",
                    "semantic_evidence_json",
                ),
            )
            for row in rows
        ]

    def get_job(self, batch_id: str, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE batch_id=? AND job_id=? AND deleted=0",
                (batch_id, job_id),
            ).fetchone()
        return (
            self._decode(
                row,
                (
                    "required_skills_json",
                    "canonical_required_skills_json",
                    "semantic_evidence_json",
                ),
            )
            if row
            else None
        )

    def save_matches(self, batch_id: str, job_id: str, matches: list[dict[str, Any]]) -> None:
        now = _now()
        with self.connect() as db:
            db.execute(
                "UPDATE matches SET deleted=1, updated_at=? "
                "WHERE batch_id=? AND job_id=? AND deleted=0",
                (now, batch_id, job_id),
            )
            db.executemany(
                """INSERT INTO matches(
                    match_id, batch_id, job_id, person_id, rank_no, score, rule_score,
                    semantic_score, explanation_json, model_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        item["match_id"],
                        batch_id,
                        job_id,
                        item["person_id"],
                        item["rank"],
                        item["score"],
                        item["rule_score"],
                        item["semantic_score"],
                        json.dumps(item["explanation"], ensure_ascii=False),
                        item["model_version"],
                        now,
                        now,
                    )
                    for item in matches
                ],
            )

    def list_matches(self, batch_id: str, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT m.*,
                    p.education, p.skill_level, p.skills_json, p.canonical_skills_json,
                    p.employment_status,
                    p.expected_salary_min, p.expected_salary_max, p.preferred_region,
                    p.years_experience, p.available_shift,
                    (SELECT decision FROM reviews r
                        WHERE r.match_id=m.match_id AND r.deleted=0
                        ORDER BY r.created_at DESC LIMIT 1) AS review_decision,
                    (SELECT reason FROM reviews r
                        WHERE r.match_id=m.match_id AND r.deleted=0
                        ORDER BY r.created_at DESC LIMIT 1) AS review_reason,
                    (SELECT outcome FROM feedback f
                        WHERE f.match_id=m.match_id AND f.deleted=0
                        ORDER BY f.created_at DESC LIMIT 1) AS feedback_outcome
                FROM matches m
                JOIN persons p ON p.batch_id=m.batch_id AND p.person_id=m.person_id
                WHERE m.batch_id=? AND m.job_id=? AND m.deleted=0
                ORDER BY m.rank_no""",
                (batch_id, job_id),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["skills"] = json.loads(item.pop("skills_json") or "[]")
            item["canonical_skills"] = json.loads(item.pop("canonical_skills_json") or "[]")
            item["explanation"] = json.loads(item.pop("explanation_json") or "{}")
            result.append(item)
        return result

    def match_exists(self, match_id: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM matches WHERE match_id=? AND deleted=0", (match_id,)
            ).fetchone()
        return bool(row)

    def add_review(self, match_id: str, decision: str, reason: str, operator: str) -> str:
        review_id = str(uuid.uuid4())
        now = _now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO reviews(
                    review_id, match_id, decision, reason, operator, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (review_id, match_id, decision, reason, operator, now, now),
            )
        return review_id

    def add_feedback(self, match_id: str, outcome: str, reason: str, operator: str) -> str:
        feedback_id = str(uuid.uuid4())
        now = _now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO feedback(
                    feedback_id, match_id, outcome, reason, operator, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (feedback_id, match_id, outcome, reason, operator, now, now),
            )
        return feedback_id

    def metrics(self, batch_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                """SELECT
                    (SELECT COUNT(*) FROM matches WHERE batch_id=? AND deleted=0) AS matches,
                    (SELECT COUNT(DISTINCT r.match_id) FROM reviews r
                        JOIN matches m ON m.match_id=r.match_id
                        WHERE m.batch_id=? AND m.deleted=0 AND r.deleted=0) AS reviewed,
                    (SELECT COUNT(DISTINCT f.match_id) FROM feedback f
                        JOIN matches m ON m.match_id=f.match_id
                        WHERE m.batch_id=? AND m.deleted=0 AND f.deleted=0) AS feedback_count,
                    (SELECT COUNT(DISTINCT r.match_id) FROM reviews r
                        JOIN matches m ON m.match_id=r.match_id
                        WHERE m.batch_id=? AND m.deleted=0 AND r.deleted=0
                        AND r.decision='accepted') AS accepted
                """,
                (batch_id, batch_id, batch_id, batch_id),
            ).fetchone()
        matches = int(row["matches"] or 0)
        reviewed = int(row["reviewed"] or 0)
        feedback_count = int(row["feedback_count"] or 0)
        accepted = int(row["accepted"] or 0)
        return {
            "matches": matches,
            "reviewed": reviewed,
            "feedback_count": feedback_count,
            "accepted": accepted,
            "review_rate": round(reviewed / matches, 4) if matches else 0,
            "feedback_completion_rate": round(feedback_count / matches, 4) if matches else 0,
            "acceptance_rate": round(accepted / reviewed, 4) if reviewed else 0,
        }
