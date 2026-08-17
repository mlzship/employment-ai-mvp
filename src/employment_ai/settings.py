from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = "就业AI智能体最小MVP"
    app_env: str = "development"
    database_path: Path = field(default_factory=lambda: PROJECT_ROOT / "runtime/employment_ai.db")
    seed_xlsx: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data/synthetic/employment_ai_demo.xlsx"
    )
    ontology_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data/ontology/employment_ontology.json"
    )
    max_upload_mb: int = 10
    session_secret: str = "local-development-secret-change-me"
    operator_password: str = "operator-demo"
    reviewer_password: str = "reviewer-demo"
    auto_seed: bool = True
    auth_disabled: bool = False
    cookie_secure: bool = False
    disabled_plugins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        disabled = tuple(
            item.strip() for item in os.getenv("DISABLED_PLUGINS", "").split(",") if item.strip()
        )
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            database_path=Path(
                os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "runtime/employment_ai.db"))
            ),
            seed_xlsx=Path(
                os.getenv("SEED_XLSX", str(PROJECT_ROOT / "data/synthetic/employment_ai_demo.xlsx"))
            ),
            ontology_path=Path(
                os.getenv(
                    "ONTOLOGY_PATH",
                    str(PROJECT_ROOT / "data/ontology/employment_ontology.json"),
                )
            ),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "10")),
            session_secret=os.getenv("SESSION_SECRET", "local-development-secret-change-me"),
            operator_password=os.getenv("OPERATOR_PASSWORD", "operator-demo"),
            reviewer_password=os.getenv("REVIEWER_PASSWORD", "reviewer-demo"),
            auto_seed=_bool_env("AUTO_SEED", True),
            auth_disabled=_bool_env("AUTH_DISABLED", False),
            cookie_secure=_bool_env("COOKIE_SECURE", False),
            disabled_plugins=disabled,
        )

    def ensure_runtime(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def validate_security(self) -> None:
        if self.app_env != "production":
            return
        weak_values = {
            "local-development-secret-change-me",
            "change-this-demo-secret-before-production",
            "operator-demo",
            "reviewer-demo",
        }
        if self.session_secret in weak_values or self.session_secret.startswith("replace-"):
            raise ValueError("production requires a non-default SESSION_SECRET")
        if len(self.session_secret) < 32:
            raise ValueError("production SESSION_SECRET must contain at least 32 characters")
        if self.operator_password in weak_values or self.operator_password.startswith("replace-"):
            raise ValueError("production requires a non-default OPERATOR_PASSWORD")
        if self.reviewer_password in weak_values or self.reviewer_password.startswith("replace-"):
            raise ValueError("production requires a non-default REVIEWER_PASSWORD")
        if self.auth_disabled:
            raise ValueError("AUTH_DISABLED cannot be enabled in production")
