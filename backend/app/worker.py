"""Entrypoint for the dedicated background worker."""

import asyncio

from app.services.background import run_worker


if __name__ == "__main__":
    asyncio.run(run_worker())
