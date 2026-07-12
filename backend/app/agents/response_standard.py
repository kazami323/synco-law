"""Shared legal-answer standard for AI agents."""

from __future__ import annotations

from typing import Any
import re

NO_DIRECT_LEXUZ_REGULATION = (
    "Прямое регулирование данного вопроса на Lex.uz не выявлено. "
    "Вывод сформирован на основании общих норм законодательства и представленной информации."
)

DEFAULT_LAWYER_NOTE = (
    "Примечание юриста: Ответ ИИ носит аналитический характер и не заменяет "
    "проверку первоисточника и финальное заключение юриста по конкретной ситуации."
)

LEGAL_RESPONSE_STANDARD = f"""
Обязательный стандарт ответа:
1. Перед ответом проверь применимое законодательство Республики Узбекистан по переданному контексту Lex.uz.
2. Не придумывай номер закона, статью, дату документа, содержание нормы или юридические последствия.
3. Если в контексте Lex.uz есть релевантная норма, укажи конкретный НПА, статью/часть/пункт при наличии, дату/номер при наличии, редакцию при наличии и ссылку Lex.uz.
4. Если конкретная норма не найдена, дословно укажи: {NO_DIRECT_LEXUZ_REGULATION}
5. Каждый ответ заверши отдельным блоком: "Примечание юриста: ...".
6. Формат правового основания: "Правовое основание: статья _ Закона Республики Узбекистан «___», № _ от ___ — Lex.uz: [ссылка]."
""".strip()


def legal_basis_lines(sources: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    lines: list[str] = []
    for source in sources[:limit]:
        title = source.get("document_title") or "НПА Республики Узбекистан"
        article = source.get("article_number")
        url = source.get("url")
        number = source.get("document_number")
        adopted_at = source.get("adopted_at")
        revision = source.get("current_revision_date")
        status = source.get("status")

        subject = f"статья {article}" if article else "фрагмент"
        number_part = f", № {number}" if number else ""
        date_part = f" от {adopted_at}" if adopted_at else ""
        line = (
            f"Правовое основание: {subject} НПА Республики Узбекистан "
            f"«{title}»{number_part}{date_part} — Lex.uz: {url}."
        )
        if revision:
            line += f" Актуальная редакция в базе: {revision}."
        if status and status != "active":
            line += f" Внимание: статус источника в базе — {status}."
        lines.append(line)
    return lines


LEXUZ_URL_RE = re.compile(r"https?://(?:www\.)?lex\.uz/[^\s)\]}>]+", re.IGNORECASE)


def sanitize_lexuz_urls(reply: str, sources: list[dict[str, Any]]) -> str:
    allowed = {
        str(source.get("url", "")).rstrip(".,;")
        for source in sources
        if source.get("url")
    }

    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        suffix = ""
        while raw and raw[-1] in ".,;:":
            suffix = raw[-1] + suffix
            raw = raw[:-1]
        if raw in allowed:
            return raw + suffix
        return "[неподтвержденная ссылка Lex.uz удалена]" + suffix

    return LEXUZ_URL_RE.sub(replace, reply)


def append_legal_standard(reply: str, sources: list[dict[str, Any]]) -> str:
    text = sanitize_lexuz_urls((reply or "").strip(), sources)
    additions: list[str] = []

    basis = legal_basis_lines(sources, limit=2)
    if basis:
        additions.extend(line for line in basis if line not in text)
    elif NO_DIRECT_LEXUZ_REGULATION not in text:
        additions.append(NO_DIRECT_LEXUZ_REGULATION)

    if "Примечание юриста:" not in text:
        additions.append(DEFAULT_LAWYER_NOTE)

    if additions:
        text = f"{text}\n\n" + "\n\n".join(additions)
    return text


def legal_basis_payload(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "text": line,
            "document_title": source.get("document_title"),
            "article_number": source.get("article_number"),
            "article_title": source.get("article_title"),
            "url": source.get("url"),
            "current_revision_date": source.get("current_revision_date"),
            "status": source.get("status"),
        }
        for line, source in zip(legal_basis_lines(sources, limit=10), sources)
    ]
