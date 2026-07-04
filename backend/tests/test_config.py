import pytest

from app.core.config import Settings


def test_development_settings_allow_local_defaults():
    settings = Settings(ENVIRONMENT="development")
    settings.validate_runtime()


def test_production_requires_strong_secret_key():
    settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="change-me-in-production",
        DATABASE_URL="postgresql+asyncpg://user:pass@db:5432/app",
        CORS_ORIGINS=["https://example.com"],
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.validate_runtime()


def test_production_rejects_localhost_database():
    settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="x" * 40,
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/app",
        CORS_ORIGINS=["https://example.com"],
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings.validate_runtime()
