from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

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
    session_secret: str = field(default="local-development-secret-change-me", repr=False)
    operator_password: str = field(default="operator-demo", repr=False)
    reviewer_password: str = field(default="reviewer-demo", repr=False)
    auto_seed: bool = True
    auth_disabled: bool = False
    cookie_secure: bool = False
    disabled_plugins: tuple[str, ...] = ()
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"
    llm_api_key: str = field(default="", repr=False)
    llm_timeout_seconds: float = 45.0
    llm_candidate_limit: int = 20
    llm_weight: float = 0.4
    llm_required: bool = False
    llm_thinking: bool = False

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
            llm_provider=os.getenv("LLM_PROVIDER", "deepseek").strip().lower(),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip(),
            llm_model=os.getenv("LLM_MODEL", "deepseek-v4-flash").strip(),
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
            llm_candidate_limit=int(os.getenv("LLM_CANDIDATE_LIMIT", "20")),
            llm_weight=float(os.getenv("LLM_WEIGHT", "0.4")),
            llm_required=_bool_env("LLM_REQUIRED", False),
            llm_thinking=_bool_env("LLM_THINKING", False),
        )

    def ensure_runtime(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def validate_security(self) -> None:
        if not self.llm_provider or not self.llm_model:
            raise ValueError("LLM_PROVIDER and LLM_MODEL cannot be empty")
        parsed_llm_url = urlparse(self.llm_base_url)
        if parsed_llm_url.scheme not in {"http", "https"} or not parsed_llm_url.netloc:
            raise ValueError("LLM_BASE_URL must be an absolute HTTP(S) URL")
        if not 0 <= self.llm_weight <= 1:
            raise ValueError("LLM_WEIGHT must be between 0 and 1")
        if not 1 <= self.llm_candidate_limit <= 50:
            raise ValueError("LLM_CANDIDATE_LIMIT must be between 1 and 50")
        if not 1 <= self.llm_timeout_seconds <= 120:
            raise ValueError("LLM_TIMEOUT_SECONDS must be between 1 and 120")
        if self.llm_required and not self.llm_api_key:
            raise ValueError("LLM_REQUIRED=true requires LLM_API_KEY")
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
        if self.llm_api_key and parsed_llm_url.scheme != "https":
            raise ValueError("production LLM_BASE_URL must use HTTPS when LLM_API_KEY is set")
