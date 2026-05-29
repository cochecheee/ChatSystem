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

    # V3.3 — Anonymous read kill-switch.
    # False (default, secure): all read endpoints require a JWT. Returning to
    #   True restores V2.x behavior for emergency rollback only.
    # gate-count is the only exception — it accepts CI_WEBHOOK_TOKEN as
    #   an alternative auth so the Security Gate composite still works
    #   without issuing JWTs to the CI runner.
    ANONYMOUS_READ_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Rewrite vendor connection strings sang SQLAlchemy async dialect.

        - `postgres://`  → `postgresql+asyncpg://`  (Render legacy form)
        - `postgresql://` (no driver) → `postgresql+asyncpg://`
        - `mysql://`     → `mysql+asyncmy://`       (XAMPP / managed MySQL)
        """
        if not v:
            return v
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        if v.startswith("mysql://") and "+asyncmy" not in v and "+aiomysql" not in v:
            return "mysql+asyncmy://" + v[len("mysql://"):]
        return v


settings = Settings()
