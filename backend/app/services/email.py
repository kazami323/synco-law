"""Email-канал уведомлений (SMTP). Без SMTP_HOST канал молча выключен."""

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger("app.email")


def email_enabled() -> bool:
    return bool(settings.SMTP_HOST)


def _send_sync(to: str, subject: str, body: str) -> None:
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = to

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_TLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.SMTP_FROM, [to], message.as_string())


async def send_email(to: str, subject: str, body: str) -> bool:
    """Шлёт письмо в thread-pool; ошибки логируются, не роняют запрос."""
    if not email_enabled():
        return False
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
        return True
    except Exception:
        logger.exception("email send failed to %s", to)
        return False
