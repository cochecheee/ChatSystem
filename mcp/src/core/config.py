from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
