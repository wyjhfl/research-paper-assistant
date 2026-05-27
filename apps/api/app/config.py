from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant"
    APP_NAME: str = "Research Paper Assistant API"
    APP_VERSION: str = "1.0.0"
    STORAGE_PATH: str = "./storage"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "local-hash"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_TIMEOUT_SECONDS: int = 30

    LLM_PROVIDER: str = "local"
    LLM_MODEL: str = "local-mock"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_TIMEOUT_SECONDS: int = 30

    PROVIDER_TIMEOUT_SECONDS: int = 60
    PROVIDER_MAX_RETRIES: int = 2
    PROVIDER_RETRY_BACKOFF_SECONDS: float = 1.0

    REAL_MODEL_REQUIRED: bool = False
    ENV: str = "development"

    CORS_ALLOWED_ORIGINS: str = "*"

    AUTH_ENABLED: bool = False
    ALLOW_DEV_USER_HEADER: bool = True
    SESSION_COOKIE_NAME: str = "research_session"
    SESSION_TTL_SECONDS: int = 604800
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = "lax"

    JOB_WORKER_ENABLED: bool = True
    JOB_POLL_INTERVAL_SECONDS: float = 1.0
    JOB_MAX_ATTEMPTS: int = 1
    JOB_STALE_RUNNING_SECONDS: int = 900

    RAG_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.1
    RAG_EVIDENCE_THRESHOLD: float = 0.2

    model_config = {"env_file": ".env", "extra": "ignore"}


def normalize_env(env_value: str) -> str:
    return env_value.strip().lower()


def is_production(s: "Settings | None" = None) -> bool:
    _settings = s or settings
    return _settings.REAL_MODEL_REQUIRED or normalize_env(_settings.ENV) == "production"


def parse_cors_allowed_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
