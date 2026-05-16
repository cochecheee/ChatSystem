from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./mcp.db"
    SECRET_KEY: str = "change-me-in-production-min-32-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-pro-preview"
    GEMINI_MAX_RETRIES: int = 3
    GITHUB_TOKEN: str = ""
    GITHUB_OWNER: str = ""
    GITHUB_REPO: str = ""
    POLLING_INTERVAL_SECONDS: int = 300
    POLLING_WORKFLOW_NAME: str = "CI Workflow"
    POLLING_BRANCH: str = "main"
    APP_ENV: str = "development"
    CI_API_KEY: str = ""        # if empty, auth disabled (dev/test mode)
    CI_WEBHOOK_TOKEN: str = ""  # if empty, webhook auth disabled
    # Comma-separated origin list for production CORS. Ignored in
    # development/testing (where allow_origins="*"). Set on Render to
    # the dashboard URL + any local-dev URL you want to allow.
    CORS_ORIGINS: str = ""

    # V2.4 — Monitor + alert
    MONITOR_ENABLED: bool = False
    MONITOR_INTERVAL_SECONDS: int = 300
    # Comma-separated list of (project_id:url) to ping, e.g.
    #   "1:https://sample-python-latest.onrender.com/health"
    MONITOR_TARGETS: str = ""
    MONITOR_DOWN_THRESHOLD: int = 2  # consecutive fails before alert

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = ""
    EMAIL_TO: str = ""

    SENTRY_DSN: str = ""

    # V2.8 — Multi-tenant runtime
    # False (default): legacy single-tenant — webhook luôn dùng
    #   GITHUB_OWNER/REPO từ env, không quan tâm payload.repository.
    #   Poller chỉ poll 1 repo configured.
    # True: webhook route theo `repository` field → lookup Project
    #   bằng github_url. Poller iterate active projects.
    #   Vẫn fallback env nếu không tìm được project (audit log warning).
    MULTI_TENANT_ENABLED: bool = False
    # Optional Fernet key cho encrypt-at-rest credentials (Phase A1).
    # Tạo: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""

    # V3.0 — Per-project RBAC kill-switch.
    # False (default): legacy single-role check; any authenticated user can
    #   access any project. Matches V2.9 behavior.
    # True: every project-scoped endpoint also checks ProjectMember; users
    #   without a membership get 403. Global role `admin` always bypasses.
    RBAC_PER_PROJECT: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Rewrite Render's `postgres://` connectionString to the SQLAlchemy
        async dialect `postgresql+asyncpg://`. SQLAlchemy 2.x dropped
        implicit `postgres://` support, and Render still emits the legacy
        form via fromDatabase.connectionString.

        Also tolerate `postgresql://` (no driver) by adding +asyncpg.
        """
        if not v:
            return v
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v


settings = Settings()
