from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "AI Legal Workspace"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    # APP_DEBUG avoids collisions with the global DEBUG=release variable used by
    # some Windows applications and CI environments.
    DEBUG: bool = Field(default=False, validation_alias="APP_DEBUG")

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_NAME: str = "auth_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None
    PUBLIC_APP_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://legal_user:secure_password@localhost:5432/legal_workspace"
    )

    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379/0"
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "contracts"
    MINIO_SECURE: bool = False

    # AI
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-4-8"
    ANTHROPIC_TIMEOUT_SECONDS: int = 90
    # Per-user: OCR-загрузки и чат делят одно окно, 10 было впритык
    AI_REQUESTS_PER_MINUTE: int = 20
    AI_DAILY_REQUESTS_PER_ORG: int = 500
    AI_DAILY_TOKENS_PER_ORG: int = 2_000_000

    # Правовая база: свой RAG по lex.uz (HTML-импорт, ключи не нужны)
    LEGAL_REFRESH_ENABLED: bool = False
    LEGAL_REFRESH_INTERVAL_HOURS: int = 24 * 7
    LEXUZ_CACHE_DIR: str = ".cache/lexuz"

    # Email-уведомления (SMTP); пустой SMTP_HOST = канал выключен
    EMAIL_NOTIFY: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "AI Legal Workspace <noreply@legal.uz>"
    SMTP_TLS: bool = True

    # Telegram-уведомления; пустой токен = канал выключен
    TELEGRAM_BOT_TOKEN: str = ""

    # E-IMZO: сервис серверной проверки подписи (DSV), опционально
    EIMZO_DSV_URL: str = ""
    EIMZO_REQUIRE_CONTENT_BINDING: bool = True
    ALLOW_STUB_SIGNATURES: bool = True

    # Optional ClamAV daemon. In production set CLAMAV_REQUIRED=true.
    CLAMAV_HOST: str = ""
    CLAMAV_PORT: int = 3310
    CLAMAV_REQUIRED: bool = False

    # API processes must disable this when a separate `python -m app.worker`
    # service is running.
    RUN_BACKGROUND_JOBS: bool = True

    # CORS (адрес фронтенда Next.js)
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://synco-law.vercel.app",
    ]

    def validate_runtime(self) -> None:
        environment = self.ENVIRONMENT.lower()
        if environment not in {"development", "test", "staging", "production"}:
            raise RuntimeError(
                "ENVIRONMENT must be development, test, staging, or production"
            )
        if environment == "production":
            if self.SECRET_KEY == "change-me-in-production" or len(self.SECRET_KEY) < 32:
                raise RuntimeError("Set a strong SECRET_KEY before production start")
            if not self.CORS_ORIGINS:
                raise RuntimeError("CORS_ORIGINS must not be empty in production")
            if "localhost" in self.DATABASE_URL:
                raise RuntimeError("DATABASE_URL must point to production database")
            if self.ALLOW_STUB_SIGNATURES:
                raise RuntimeError("Disable ALLOW_STUB_SIGNATURES in production")
            if not self.EIMZO_DSV_URL:
                raise RuntimeError("Set EIMZO_DSV_URL before production start")
            if not self.COOKIE_SECURE:
                raise RuntimeError("COOKIE_SECURE must be true in production")
            if not self.CLAMAV_REQUIRED or not self.CLAMAV_HOST:
                raise RuntimeError("Configure required ClamAV scanning in production")


settings = Settings()
