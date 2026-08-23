"""Экспорт документа в DOCX и PDF (ТЗ, раздел 5).

Две сборки:

* clean   — чистая версия для контрагента: только текст договора;
* working — рабочая версия для внутреннего использования: тот же текст плюс
            вердикты по пунктам, решения юриста, расхождения Модуля 2, риски
            Модуля 3 и комментарии.

Отправить контрагенту рабочую версию с внутренними замечаниями — это утечка
позиции на переговорах, поэтому режимы разделены жёстко, а не галочкой
«показывать комментарии».
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime, timezone

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from app.agents.risk_agent import RISK_CATEGORIES, RISK_LEVELS
from app.core.document_types import type_title
from app.core.statuses import status_title
from app.services.logic_check import LOGIC_CATEGORIES

# Строка-заголовок в «чистой» версии: капслок или «Раздел N».
HEADING_RE = re.compile(r"^(?:раздел|глава|статья)\s|^[^a-zа-яё]{4,80}$", re.IGNORECASE)

VERDICT_TITLES = {
    "compliant": "Соответствует",
    "conflicts": "Противоречит",
    "attention": "Требует внимания",
    "no_norm": "Норма не найдена",
}

DECISION_TITLES = {
    "confirm": "Подтверждено",
    "edit": "Изменено",
    "comment": "Комментарий",
    "defer": "Отложено",
}

# Шрифт с кириллицей для PDF. В образе он ставится пакетом fonts-dejavu-core,
# на машине разработчика берётся системный.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\segoeui.ttf",
    "/Library/Fonts/Arial.ttf",
)
FONT_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\segoeuib.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)


class ExportError(Exception):
    """Экспорт невозможен по причине, которую нужно показать пользователю."""


def build_docx(payload: dict) -> bytes:
    """Собирает DOCX. payload — результат build_payload()."""
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(payload["title"])
    run.bold = True
    run.font.size = Pt(16)

    meta = document.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta.add_run(payload["meta_line"])
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    document.add_paragraph()

    for clause in payload["clauses"]:
        paragraph = document.add_paragraph()
        text = f"{clause['prefix']}{clause['content']}" if clause["prefix"] else clause["content"]
        clause_run = paragraph.add_run(text)
        if clause["is_heading"]:
            clause_run.bold = True

        if not payload["working"]:
            continue
        for note in clause["notes"]:
            note_paragraph = document.add_paragraph()
            note_paragraph.paragraph_format.left_indent = Pt(18)
            note_run = note_paragraph.add_run(note)
            note_run.italic = True
            note_run.font.size = Pt(10)
            note_run.font.color.rgb = RGBColor(0x88, 0x44, 0x00)

    if payload["working"]:
        for section in payload["sections"]:
            document.add_page_break()
            title = document.add_paragraph()
            title_run = title.add_run(section["title"])
            title_run.bold = True
            title_run.font.size = Pt(14)
            if not section["lines"]:
                document.add_paragraph("Замечаний нет.")
            for line in section["lines"]:
                document.add_paragraph(line, style="List Bullet")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_pdf(payload: dict) -> bytes:
    """Собирает PDF. Требует reportlab и шрифт с поддержкой кириллицы."""
    try:
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise ExportError(
            "PDF-экспорт недоступен: не установлен reportlab"
        ) from exc

    regular = _first_existing(FONT_CANDIDATES)
    if regular is None:
        raise ExportError(
            "PDF-экспорт недоступен: в системе нет шрифта с поддержкой кириллицы"
        )
    bold = _first_existing(FONT_BOLD_CANDIDATES) or regular

    if "DocFont" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DocFont", regular))
        pdfmetrics.registerFont(TTFont("DocFont-Bold", bold))

    base = getSampleStyleSheet()["Normal"]
    body = ParagraphStyle(
        "Body", parent=base, fontName="DocFont", fontSize=11, leading=15,
        spaceAfter=6,
    )
    heading = ParagraphStyle(
        "Heading", parent=body, fontName="DocFont-Bold", fontSize=12, spaceBefore=10,
    )
    title_style = ParagraphStyle(
        "Title", parent=body, fontName="DocFont-Bold", fontSize=16,
        alignment=TA_CENTER, spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "Meta", parent=body, fontName="DocFont", fontSize=9,
        alignment=TA_CENTER, textColor="#666666", spaceAfter=14,
    )
    note_style = ParagraphStyle(
        "Note", parent=body, fontName="DocFont", fontSize=9,
        leftIndent=14, textColor="#884400", spaceAfter=3,
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=payload["title"],
    )

    flow = [
        Paragraph(_escape(payload["title"]), title_style),
        Paragraph(_escape(payload["meta_line"]), meta_style),
    ]
    for clause in payload["clauses"]:
        text = f"{clause['prefix']}{clause['content']}" if clause["prefix"] else clause["content"]
        flow.append(
            Paragraph(_escape(text), heading if clause["is_heading"] else body)
        )
        if payload["working"]:
            for note in clause["notes"]:
                flow.append(Paragraph(_escape(note), note_style))

    if payload["working"]:
        for section in payload["sections"]:
            flow.append(PageBreak())
            flow.append(Paragraph(_escape(section["title"]), heading))
            flow.append(Spacer(1, 4))
            if not section["lines"]:
                flow.append(Paragraph("Замечаний нет.", body))
            for line in section["lines"]:
                flow.append(Paragraph("• " + _escape(line), body))

    document.build(flow)
    return buffer.getvalue()


def build_payload(
    contract,
    clauses: list,
    *,
    working: bool,
    checks: dict | None = None,
    decisions: dict | None = None,
    logic_findings: list | None = None,
    risk_findings: list | None = None,
    comments: list | None = None,
) -> dict:
    """Готовит данные для обеих сборок, чтобы DOCX и PDF не разъезжались."""
    checks = checks or {}
    decisions = decisions or {}

    clause_items = []

    if not working:
        # Контрагенту уходит текст документа как есть, без реконструкции.
        for paragraph in (contract.content or "").split("\n"):
            text = paragraph.strip()
            if not text:
                continue
            clause_items.append(
                {
                    "anchor": "",
                    "prefix": "",
                    "content": text,
                    "is_heading": bool(HEADING_RE.match(text)),
                    "notes": [],
                }
            )
        return {
            "title": contract.title,
            "meta_line": _meta_line(contract, working=False),
            "clauses": clause_items,
            "sections": [],
            "working": False,
        }

    for clause in sorted(clauses, key=lambda item: item.position):
        prefix = f"{clause.number}. " if clause.number else ""
        if not prefix and clause.anchor and not clause.anchor.startswith(("§", "преамбула")):
            prefix = f"{clause.anchor}) "

        notes: list[str] = []
        if working:
            check = checks.get(clause.id)
            if check is not None:
                verdict = VERDICT_TITLES.get(check.verdict, check.verdict)
                line = f"Проверка: {verdict}"
                if check.rationale:
                    line += f" — {check.rationale}"
                notes.append(line)
                for source in check.sources or []:
                    notes.append(
                        "Основание: "
                        + " ".join(
                            part
                            for part in [
                                source.get("document_title"),
                                f"ст. {source['article_number']}"
                                if source.get("article_number")
                                else None,
                                f"(редакция {source['current_revision_date']})"
                                if source.get("current_revision_date")
                                else None,
                                source.get("url"),
                            ]
                            if part
                        )
                    )
                if check.suggested_text:
                    notes.append(f"Предложенная формулировка: {check.suggested_text}")

            decision = decisions.get(clause.id)
            if decision is not None:
                action = DECISION_TITLES.get(decision.action, decision.action)
                who = decision.decided_by_name or "юрист"
                when = (
                    decision.created_at.strftime("%d.%m.%Y %H:%M")
                    if decision.created_at
                    else ""
                )
                line = f"Решение юриста: {action} — {who} {when}".strip()
                if decision.comment:
                    line += f". {decision.comment}"
                notes.append(line)

        clause_items.append(
            {
                "anchor": clause.anchor,
                "prefix": prefix,
                "content": clause.content,
                "is_heading": bool(
                    clause.title and clause.content.strip() == clause.title.strip()
                ),
                "notes": notes,
            }
        )

    sections = []
    if working:
        sections.append(
            {
                "title": "Расхождения внутри документа (Модуль 2)",
                "lines": [
                    _logic_line(finding) for finding in (logic_findings or [])
                ],
            }
        )
        sections.append(
            {
                "title": "Риски (Модуль 3)",
                "lines": [_risk_line(finding) for finding in (risk_findings or [])],
            }
        )
        if comments:
            sections.append(
                {
                    "title": "Комментарии",
                    "lines": [
                        f"{comment.author_name or 'Пользователь'}"
                        f"{f' (п. {comment.clause_anchor})' if getattr(comment, 'clause_anchor', None) else ''}"
                        f": {comment.text}"
                        for comment in comments
                    ],
                }
            )

    return {
        "title": contract.title,
        "meta_line": _meta_line(contract, working=working),
        "clauses": clause_items,
        "sections": sections,
        "working": working,
    }


def _meta_line(contract, *, working: bool) -> str:
    parts = [
        type_title(contract.contract_type),
        f"статус: {status_title(contract.status)}",
    ]
    if contract.counterparty:
        parts.append(f"контрагент: {contract.counterparty}")
    parts.append(datetime.now(timezone.utc).strftime("выгружено %d.%m.%Y"))
    if working:
        parts.append("РАБОЧАЯ ВЕРСИЯ — не для передачи контрагенту")
    return " · ".join(parts)


def _logic_line(finding) -> str:
    category = LOGIC_CATEGORIES.get(finding.category, finding.category)
    anchors = ", ".join(finding.clause_anchors or [])
    line = f"{category} (пункты {anchors}): {finding.description}"
    if finding.suggestion:
        line += f" Предложение: {finding.suggestion}"
    return line


def _risk_line(finding) -> str:
    category = RISK_CATEGORIES.get(finding.category, finding.category)
    level = RISK_LEVELS.get(finding.level, finding.level)
    line = f"{category}, риск {level}: {finding.description}"
    if finding.consequence:
        line += f" Последствия: {finding.consequence}"
    if finding.mitigation:
        line += f" Устранение: {finding.mitigation}"
    if finding.clause_anchors:
        line += f" (пункты {', '.join(finding.clause_anchors)})"
    return line


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _first_existing(paths) -> str | None:
    for path in paths:
        if os.path.exists(path):
            return path
    return None
