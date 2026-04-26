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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
