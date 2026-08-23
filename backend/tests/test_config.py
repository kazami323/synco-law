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


def _deployed(**overrides) -> Settings:
    """Конфиг живого стенда: как в deploy/.env.production."""
    base = dict(
        ENVIRONMENT="staging",
        SECRET_KEY="x" * 64,
        DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/app",
        CORS_ORIGINS=["https://app.example.uz"],
        COOKIE_SECURE=True,
        ALLOW_STUB_SIGNATURES=False,
        CLAMAV_HOST="clamav",
        CLAMAV_REQUIRED=True,
    )
    return Settings(**{**base, **overrides})


def test_staging_deployment_starts():
    """Боевой стенд стоит на ENVIRONMENT=staging, пока не подключён E-IMZO DSV:
    защитные проверки не должны мешать ему подниматься."""
    _deployed().validate_runtime()


@pytest.mark.parametrize(
    "override, marker",
    [
        ({"ALLOW_STUB_SIGNATURES": True}, "ALLOW_STUB_SIGNATURES"),
        ({"COOKIE_SECURE": False}, "COOKIE_SECURE"),
        ({"SECRET_KEY": "change-me-in-production"}, "SECRET_KEY"),
        ({"CLAMAV_REQUIRED": False}, "ClamAV"),
        (
            {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/app"},
            "DATABASE_URL",
        ),
        ({"CORS_ORIGINS": []}, "CORS_ORIGINS"),
    ],
)
def test_staging_enforces_production_guardrails(override, marker):
    """Раньше ENVIRONMENT=staging отключал весь блок проверок разом: включение
    ALLOW_STUB_SIGNATURES на живом сервере прошло бы молча, а это подделка
    подписи под договором."""
    with pytest.raises(RuntimeError, match=marker):
        _deployed(**override).validate_runtime()


def test_dsv_url_required_only_in_production():
    """Единственное послабление staging: подпись пока проверять нечем."""
    _deployed(EIMZO_DSV_URL="").validate_runtime()
    with pytest.raises(RuntimeError, match="EIMZO_DSV_URL"):
        _deployed(ENVIRONMENT="production", EIMZO_DSV_URL="").validate_runtime()
