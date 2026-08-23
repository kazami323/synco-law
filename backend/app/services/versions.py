"""Сравнение версий документа и откат (ТЗ, раздел 5).

Сравнение построчное: договор — это текст, где юриста интересует, какая
формулировка изменилась, а не какие символы. Результат отдаётся блоками, чтобы
интерфейс показывал изменения рядом, а не двумя простынями.
"""

from __future__ import annotations

import difflib
import re

# Потолок на число строк в сравнении. difflib квадратичен на похожих строках,
# и договор из десятков тысяч одинаковых строк способен занять event loop на
# минуты — это отказ в обслуживании для всех организаций сразу.
MAX_DIFF_LINES = 6000


class DiffTooLarge(Exception):
    """Документ слишком велик для построчного сравнения."""


def split_lines(text: str | None) -> list[str]:
    """Режет текст на смысловые строки, отбрасывая пустые."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in normalized.split("\n") if line.strip()]


def diff_versions(old_text: str | None, new_text: str | None) -> dict:
    """Различия между двумя версиями.

    blocks: [{type, old_start, new_start, old_lines, new_lines}]
      equal   — совпадающий фрагмент
      insert  — добавлено
      delete  — удалено
      replace — переформулировано
    """
    old_lines = split_lines(old_text)
    new_lines = split_lines(new_text)
    if max(len(old_lines), len(new_lines)) > MAX_DIFF_LINES:
        raise DiffTooLarge(
            f"Документ слишком велик для построчного сравнения: "
            f"{max(len(old_lines), len(new_lines))} строк при пределе {MAX_DIFF_LINES}."
        )
    # autojunk оставлен включённым намеренно: именно он гасит квадратичное
    # поведение на повторяющихся строках, которых в договорах много.
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

    blocks: list[dict] = []
    added = removed = changed = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        block = {
            "type": tag,
            "old_start": i1 + 1,
            "new_start": j1 + 1,
            "old_lines": old_lines[i1:i2],
            "new_lines": new_lines[j1:j2],
        }
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            changed += max(i2 - i1, j2 - j1)
            block["inline"] = [
                inline_diff(old, new)
                for old, new in zip(old_lines[i1:i2], new_lines[j1:j2])
            ]
        blocks.append(block)

    return {
        "blocks": blocks,
        "summary": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "identical": added == removed == changed == 0,
        },
    }


def inline_diff(old_line: str, new_line: str) -> dict:
    """Пословные различия внутри переформулированной строки."""
    old_words = _words(old_line)
    new_words = _words(new_line)
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    old_parts: list[dict] = []
    new_parts: list[dict] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("equal", "delete", "replace"):
            chunk = "".join(old_words[i1:i2])
            if chunk:
                old_parts.append(
                    {"text": chunk, "changed": tag != "equal"}
                )
        if tag in ("equal", "insert", "replace"):
            chunk = "".join(new_words[j1:j2])
            if chunk:
                new_parts.append(
                    {"text": chunk, "changed": tag != "equal"}
                )
    return {"old": old_parts, "new": new_parts}


def _words(line: str) -> list[str]:
    return re.findall(r"\s+|[^\s]+", line or "")
