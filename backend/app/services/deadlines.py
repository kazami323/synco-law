import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Contract, ContractDeadline

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

NUMERIC_DATE_RE = re.compile(
    r"(?<!\d)(?P<a>\d{1,4})[./-](?P<b>\d{1,2})[./-](?P<c>\d{2,4})(?!\d)"
)
TEXT_MONTH_RE = re.compile(
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)


def days_left(deadline_date: date, today: date | None = None) -> int:
    return (deadline_date - (today or date.today())).days


def infer_deadline_type(context: str) -> str:
    lower = context.lower()
    if any(token in lower for token in ("оплат", "payment", "счет", "счёт")):
        return "payment"
    if any(token in lower for token in ("постав", "delivery", "товар", "услуг")):
        return "delivery"
    if any(token in lower for token in ("отчет", "отчёт", "report")):
        return "report"
    return "other"


def _parse_numeric_date(match: re.Match[str]) -> date | None:
    a = int(match.group("a"))
    b = int(match.group("b"))
    c = int(match.group("c"))
    try:
        if a > 31:
            parsed = date(a, b, c)
        else:
            if c < 100:
                # «1.2.3» и прочие номера пунктов не считаем датами
                if c < 20:
                    return None
                c += 2000
            parsed = date(c, b, a)
    except ValueError:
        return None
    # Отсекаем неправдоподобные годы (номера договоров, опечатки)
    if not 2000 <= parsed.year <= 2100:
        return None
    return parsed


def extract_deadlines_from_text(text: str | None) -> list[dict[str, date | str]]:
    if not text:
        return []

    found: dict[tuple[date, str], dict[str, date | str]] = {}
    for match in NUMERIC_DATE_RE.finditer(text):
        parsed = _parse_numeric_date(match)
        if parsed is None:
            continue
        start = max(match.start() - 80, 0)
        end = min(match.end() + 80, len(text))
        deadline_type = infer_deadline_type(text[start:end])
        found[(parsed, deadline_type)] = {
            "deadline_date": parsed,
            "type": deadline_type,
        }

    for match in TEXT_MONTH_RE.finditer(text):
        try:
            parsed = date(
                int(match.group("year")),
                MONTHS[match.group("month").lower()],
                int(match.group("day")),
            )
        except ValueError:
            continue
        start = max(match.start() - 80, 0)
        end = min(match.end() + 80, len(text))
        deadline_type = infer_deadline_type(text[start:end])
        found[(parsed, deadline_type)] = {
            "deadline_date": parsed,
            "type": deadline_type,
        }

    return sorted(found.values(), key=lambda item: item["deadline_date"])


# Автопарсинг добавляет только «живые» сроки: не старше месяца и не дальше
# 10 лет — даты заключения старых договоров в тексте сроками не считаем
PARSE_PAST_GRACE_DAYS = 30
PARSE_FUTURE_HORIZON_DAYS = 3650


def actionable_window(today: date | None = None) -> tuple[date, date]:
    current = today or date.today()
    return (
        current - timedelta(days=PARSE_PAST_GRACE_DAYS),
        current + timedelta(days=PARSE_FUTURE_HORIZON_DAYS),
    )


async def add_parsed_deadlines(db: AsyncSession, contract: Contract) -> int:
    low, high = actionable_window()
    parsed = [
        item
        for item in extract_deadlines_from_text(contract.content)
        if low <= item["deadline_date"] <= high
    ]
    if not parsed:
        return 0

    existing_rows = await db.execute(
        select(ContractDeadline).where(ContractDeadline.contract_id == contract.id)
    )
    existing = {
        (row.deadline_date, row.deadline_type) for row in existing_rows.scalars().all()
    }
    added = 0
    for item in parsed:
        key = (item["deadline_date"], item["type"])
        if key in existing:
            continue
        db.add(
            ContractDeadline(
                contract_id=contract.id,
                deadline_date=item["deadline_date"],
                deadline_type=item["type"],
            )
        )
        existing.add(key)
        added += 1
    return added
