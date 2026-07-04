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
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 дней

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

    # External APIs
    LEX_UZ_API_KEY: str = ""
    EMAIL_NOTIFY: bool = False

    # CORS (адрес фронтенда Next.js)
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

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


settings = Settings()
