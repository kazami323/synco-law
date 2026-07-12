"""Prepare an isolated E2E database and run the API on port 8010."""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import uvicorn
from alembic import command
from alembic.config import Config


def _database_url() -> str:
    configured = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://legal_user:secure_password@localhost:5432/legal_workspace_e2e",
    )
    parts = urlsplit(configured.replace("+asyncpg", ""))
    if parts.path.rstrip("/") != "/legal_workspace_e2e":
        raise RuntimeError("E2E server must use the legal_workspace_e2e database")
    return configured


def _prepare_database(url: str) -> None:
    sync_url = url.replace("+asyncpg", "")
    parts = urlsplit(sync_url)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    connection = psycopg2.connect(admin_url)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", ("legal_workspace_e2e",)
        )
        if cursor.fetchone() is None:
            cursor.execute('CREATE DATABASE "legal_workspace_e2e"')
    connection.close()

    os.environ["DATABASE_URL"] = url
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "head")


if __name__ == "__main__":
    database_url = _database_url()
    _prepare_database(database_url)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8010, log_level="warning")
