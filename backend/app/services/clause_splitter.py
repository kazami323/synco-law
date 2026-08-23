"""Разбивка документа на структурные единицы (ТЗ, раздел 4, Модуль 1).

Чистые функции без БД: текст на входе, список пунктов на выходе. Разбивка
детерминированная — LLM здесь не используется, потому что нумерация пунктов
это разметка, а не смысл, и юрист должен получать один и тот же результат
при каждом запуске.

Разбивщик рассчитан в том числе на грязный текст после OCR скана: висячие
переносы, номера страниц отдельной строкой, неразрывные пробелы.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# Максимальная глубина дерева: раздел -> пункт -> подпункт -> под-подпункт.
MAX_LEVEL = 4

# Потолок на число пунктов. Договор на 2000 пунктов юрист всё равно не пройдёт
# вручную, а без предела текст из десятков тысяч абзацев заводил в базу столько
# же строк и рассылался пачками в модель, выжигая дневную квоту организации.
MAX_CLAUSES = 2000

NBSP = " "
SOFT_HYPHEN = "­"

# «1.», «1.1», «1.1.1.» в начале строки.
#
# Многоуровневый номер («1.1») распознаётся и без точки на конце — так пишут в
# договорах. Одноуровневый номер точку требует обязательно, иначе разбивщик
# принял бы за пункт любую строку, начинающуюся с числа: «12 месяцев с даты».
RE_NUMERIC = re.compile(
    r"^((?:\d{1,2}(?:\.\d{1,3}){1,3})|(?:\d{1,2}(?=\.)))\.?\s+(?=\S)"
)

# «Раздел 3», «Глава II», «Статья 5» — заголовок верхнего уровня.
RE_SECTION_WORD = re.compile(
    r"^(раздел|глава|статья|часть)\s+([IVXLC]+|\d{1,2})\.?\s*(.*)$",
    re.IGNORECASE,
)

# «I.», «IV.» — римская нумерация разделов.
RE_ROMAN = re.compile(r"^([IVXLC]{1,6})\.\s+(?=\S)")

# «а)», «б)», «1)» — подпункт-перечисление.
RE_LETTER = re.compile(r"^([а-яёa-z]|\d{1,2})\)\s+(?=\S)", re.IGNORECASE)

# Строка-мусор от OCR: одинокий номер страницы или колонтитул из дефисов.
RE_PAGE_NOISE = re.compile(
    r"^[\s\-—_.]*(?:стр\.?|страница)?[\s\-—_.]*\d{1,3}[\s\-—_.]*$",
    re.IGNORECASE,
)

# Заголовок без номера, набранный капслоком: «ПРЕДМЕТ ДОГОВОРА».
RE_CAPS_HEADING = re.compile(r"^[^a-zа-яё]{4,80}$")

PREAMBLE_ANCHOR = "преамбула"


@dataclass
class ParsedClause:
    anchor: str
    number: str | None
    level: int
    title: str | None
    content: str
    position: int
    # Границы пункта в НОРМАЛИЗОВАННОМ тексте (см. normalize). По ним правка
    # пункта вставляется ровно на своё место. Пересобирать документ из пунктов
    # для этого нельзя: реконструкция теряет слово «Раздел», римскую нумерацию
    # и маркеры подпунктов, а на следующем разборе схлопывает подпункты в
    # родителя вместе с подтверждениями юриста.
    start_offset: int = 0
    end_offset: int = 0
    parent_anchor: str | None = None
    children: list["ParsedClause"] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        return content_hash(self.content)


def normalize(text: str) -> str:
    """Приводит текст к виду, пригодному для разбора."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(NBSP, " ").replace("\t", " ").replace(SOFT_HYPHEN, "")
    # Висячий дефис-перенос в конце строки после OCR: «постав-\nщик».
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    lines = [re.sub(r"[ ]{2,}", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)


def content_hash(text: str) -> str:
    """Хеш пункта, устойчивый к переносам и лишним пробелам.

    Нужен, чтобы отличать «пункт переписали» от «пункт переехал»: подтверждение
    юриста действует, пока текст пункта не изменился по существу.
    """
    normalized = re.sub(r"\s+", " ", (text or "")).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def split_document(text: str) -> list[ParsedClause]:
    """Разбивает документ на плоский список пунктов в порядке следования.

    Родительские связи проставлены через parent_anchor; дерево собирается
    функцией build_tree.
    """
    text = normalize(text)
    if not text.strip():
        return []

    blocks = _collect_blocks(text)
    structured = [block for block in blocks if block["kind"] != "preamble"]
    # Если разметки почти нет, нумерация ненадёжна: режем по абзацам, иначе
    # весь документ схлопнется в один гигантский «пункт».
    if len(structured) < 2:
        return _fallback_paragraphs(text)

    clauses: list[ParsedClause] = []
    used_anchors: set[str] = set()
    stack: dict[int, str] = {}  # уровень -> якорь последнего пункта этого уровня
    surrogate = 0

    for block in blocks:
        content = block["content"].strip()
        if not content:
            continue

        level = block["level"]
        parent_anchor = None
        for parent_level in range(level - 1, 0, -1):
            if parent_level in stack:
                parent_anchor = stack[parent_level]
                break

        if block["number"]:
            anchor = _unique(block["number"], used_anchors)
        elif block["kind"] == "preamble":
            anchor = _unique(PREAMBLE_ANCHOR, used_anchors)
        elif block["kind"] == "letter" and block.get("marker"):
            # «а)» внутри пункта 4.3 получает якорь «4.3.а» — так на него
            # ссылаются и юристы, и Модуль 2 при разборе перекрёстных ссылок.
            base = block["marker"]
            if parent_anchor:
                base = f"{parent_anchor}.{block['marker']}"
            anchor = _unique(base, used_anchors)
        else:
            surrogate += 1
            anchor = _unique(f"§{surrogate}", used_anchors)

        clauses.append(
            ParsedClause(
                anchor=anchor,
                number=block["number"],
                level=level,
                title=block["title"],
                content=content,
                position=len(clauses),
                start_offset=block["start"],
                end_offset=block["end"],
                parent_anchor=parent_anchor,
            )
        )
        stack[level] = anchor
        for deeper in [lvl for lvl in list(stack) if lvl > level]:
            stack.pop(deeper, None)
        if len(clauses) >= MAX_CLAUSES:
            break

    return clauses


def build_tree(clauses: list[ParsedClause]) -> list[ParsedClause]:
    """Собирает дерево из плоского списка (для отдачи в интерфейс)."""
    by_anchor = {clause.anchor: clause for clause in clauses}
    for clause in clauses:
        clause.children = []
    roots: list[ParsedClause] = []
    for clause in clauses:
        parent = by_anchor.get(clause.parent_anchor or "")
        if parent is None:
            roots.append(clause)
        else:
            parent.children.append(clause)
    return roots


def find_references(text: str) -> list[str]:
    """Находит перекрёстные ссылки вида «п. 5.4», «пункт 3», «раздел 7».

    Используется Модулем 2 для поиска битых ссылок: найденное сопоставляется
    с реальными якорями документа.
    """
    pattern = re.compile(
        r"(?:пп\.|п\.|подпункт\w*|пункт\w*|раздел\w*|разд\.)"
        r"\s*(?:№|N)?\s*"
        r"((?:\d{1,2}(?:\.\d{1,3}){0,3})(?:\s*(?:,|и)\s*\d{1,2}(?:\.\d{1,3}){0,3})*)",
        re.IGNORECASE,
    )
    refs: list[str] = []
    for match in pattern.finditer(text or ""):
        for part in re.split(r"[,и]", match.group(1)):
            ref = part.strip().rstrip(".")
            if ref:
                refs.append(ref)
    return refs


# --------------------------------------------------------------------------
# Внутреннее
# --------------------------------------------------------------------------


def _collect_blocks(text: str) -> list[dict]:
    """Проходит по строкам и собирает блоки «маркер + текст до следующего»."""
    blocks: list[dict] = []
    current: dict | None = None
    preamble: list[str] = []
    # Глубина последнего нумерованного пункта: подпункты «а)» вкладываются в него.
    numeric_depth = 0
    offset = 0

    for line in text.split("\n"):
        line_start = offset
        offset += len(line) + 1  # +1 — символ перевода строки
        stripped = line.strip()
        if not stripped:
            (current["lines"] if current is not None else preamble).append("")
            continue
        if RE_PAGE_NOISE.match(stripped):
            continue

        marker = _match_marker(stripped, numeric_depth)
        if marker is None:
            (current["lines"] if current is not None else preamble).append(stripped)
            continue

        if current is not None:
            current["end"] = line_start
            blocks.append(current)
        current = {
            "start": line_start,
            "end": len(text),
            "kind": marker["kind"],
            "number": marker["number"],
            "marker": marker.get("marker"),
            "level": marker["level"],
            "title": marker["title"],
            "lines": [marker["rest"]] if marker["rest"] else [],
        }
        if marker["kind"] == "numeric":
            numeric_depth = marker["level"]

    if current is not None:
        current["end"] = len(text)
        blocks.append(current)

    result: list[dict] = []
    preamble_text = _join(preamble)
    if preamble_text:
        result.append(
            {
                "kind": "preamble",
                "number": None,
                "marker": None,
                "level": 1,
                "title": None,
                "content": preamble_text,
                "start": 0,
                "end": blocks[0]["start"] if blocks else len(text),
            }
        )
    for block in blocks:
        content = _join(block["lines"])
        result.append(
            {
                "kind": block["kind"],
                "number": block["number"],
                "marker": block["marker"],
                "level": block["level"],
                "title": block["title"] or _derive_title(content),
                "content": content,
                "start": block["start"],
                "end": block["end"],
            }
        )
    return result


def _derive_title(content: str) -> str | None:
    """Заголовком считается только однострочный блок вроде «2. ЦЕНА ТОВАРА».

    Проверять первую строку многострочного пункта нельзя: у пункта «1.1.
    Поставщик обязуется поставить оборудование, а Покупатель принять и…»
    первая строка обрывается по ширине страницы и выглядит как заголовок.
    """
    lines = [line for line in content.split("\n") if line.strip()]
    if len(lines) != 1:
        return None
    return lines[0].strip() if _looks_like_heading(lines[0].strip()) else None


def _match_marker(line: str, numeric_depth: int) -> dict | None:
    """Определяет, начинается ли строка новым структурным маркером."""
    section = RE_SECTION_WORD.match(line)
    if section:
        number = section.group(2)
        tail = section.group(3).strip()
        return {
            "kind": "section",
            "number": number if number.isdigit() else None,
            "level": 1,
            "title": tail or None,
            "rest": tail,
        }

    numeric = RE_NUMERIC.match(line)
    if numeric:
        number = numeric.group(1).rstrip(".")
        return {
            "kind": "numeric",
            "number": number,
            "level": min(number.count(".") + 1, MAX_LEVEL),
            "title": None,  # заголовок выводится позже, по всему блоку
            "rest": line[numeric.end():].strip(),
        }

    roman = RE_ROMAN.match(line)
    if roman:
        return {
            "kind": "roman",
            "number": None,
            "level": 1,
            "title": None,
            "rest": line[roman.end():].strip(),
        }

    letter = RE_LETTER.match(line)
    if letter:
        rest = line[letter.end():].strip()
        return {
            "kind": "letter",
            "number": None,
            "marker": letter.group(1).lower(),
            "level": min(max(numeric_depth, 1) + 1, MAX_LEVEL),
            "title": None,
            "rest": rest,
        }

    if RE_CAPS_HEADING.match(line) and len(line.split()) <= 8:
        return {
            "kind": "caps",
            "number": None,
            "level": 1,
            "title": line.strip(),
            "rest": line.strip(),
        }

    return None


def _looks_like_heading(text: str) -> bool:
    """Короткая строка без знака препинания в конце — заголовок, а не условие."""
    if not text or len(text) > 90:
        return False
    if text.endswith((".", ";", ":", ",")):
        return False
    return len(text.split()) <= 9


def _join(lines: list[str]) -> str:
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _unique(anchor: str, used: set[str]) -> str:
    candidate = anchor
    suffix = 2
    while candidate in used:
        candidate = f"{anchor}#{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _fallback_paragraphs(text: str) -> list[ParsedClause]:
    """Документ без нумерации: каждый абзац — отдельный пункт.

    Так интерфейс «пункт за пунктом» работает и для сканов, где нумерация
    не распозналась.
    """
    clauses: list[ParsedClause] = []
    used: set[str] = set()
    cursor = 0
    for raw in re.split(r"(\n\s*\n)", text):
        chunk = raw.strip()
        if not chunk:
            cursor += len(raw)
            continue
        start = cursor + (len(raw) - len(raw.lstrip()))
        clauses.append(
            ParsedClause(
                anchor=_unique(f"§{len(clauses) + 1}", used),
                number=None,
                level=1,
                title=None,
                content=chunk,
                position=len(clauses),
                start_offset=start,
                end_offset=start + len(chunk),
                parent_anchor=None,
            )
        )
        cursor += len(raw)
        if len(clauses) >= MAX_CLAUSES:
            break
    return clauses
