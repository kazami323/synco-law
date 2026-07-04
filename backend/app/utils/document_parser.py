"""Извлечение текста контракта из загружаемых файлов (PDF/DOCX/TXT)."""

import io

from docx import Document
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt")


def parse_file(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return parse_pdf(data)
    if name.endswith(".docx"):
        return parse_docx(data)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="replace").strip()
    raise ValueError(
        f"Неподдерживаемый формат файла. Допустимы: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


def parse_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def parse_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()
