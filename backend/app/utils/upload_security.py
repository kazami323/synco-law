"""Upload validation, archive-bomb protection and optional ClamAV scanning."""

from __future__ import annotations

import asyncio
import re
import struct
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2_000
MAX_UNCOMPRESSED_SIZE = 80 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class UploadSecurityError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


async def read_limited_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise UploadSecurityError("Файл больше 20 МБ", status_code=413)
        chunks.append(chunk)
    return b"".join(chunks)


def sanitize_filename(filename: str | None) -> str:
    name = Path(filename or "document").name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip(" .")
    name = re.sub(r"[<>:\"/\\|?*]", "_", name)
    if not name:
        name = "document"
    return name[:180]


def validate_file_signature(filename: str, data: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadSecurityError("Неподдерживаемый формат. Допустимы PDF, DOCX и TXT")
    if not data:
        raise UploadSecurityError("Файл пуст")

    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise UploadSecurityError("Содержимое файла не соответствует формату PDF")
    if extension == ".docx":
        if not data.startswith(b"PK"):
            raise UploadSecurityError("Содержимое файла не соответствует формату DOCX")
        _validate_docx_archive(data)
    if extension == ".txt":
        if b"\x00" in data[:4096]:
            raise UploadSecurityError("TXT-файл содержит бинарные данные")
        data.decode("utf-8", errors="strict")
    return extension


def _validate_docx_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise UploadSecurityError("DOCX содержит слишком много элементов")
            total = 0
            names = set()
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                if normalized.startswith("/") or "../" in f"/{normalized}":
                    raise UploadSecurityError("DOCX содержит небезопасный путь")
                total += info.file_size
                if total > MAX_UNCOMPRESSED_SIZE:
                    raise UploadSecurityError("DOCX слишком велик после распаковки")
                names.add(normalized)
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UploadSecurityError("Некорректная структура DOCX")
    except zipfile.BadZipFile as exc:
        raise UploadSecurityError("Повреждённый DOCX") from exc


async def scan_for_malware(data: bytes) -> None:
    if not settings.CLAMAV_HOST:
        if settings.CLAMAV_REQUIRED:
            raise UploadSecurityError(
                "Антивирусная проверка временно недоступна", status_code=503
            )
        return
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.CLAMAV_HOST, settings.CLAMAV_PORT),
            timeout=5,
        )
        writer.write(b"zINSTREAM\0")
        for offset in range(0, len(data), 64 * 1024):
            chunk = data[offset : offset + 64 * 1024]
            writer.write(struct.pack(">I", len(chunk)) + chunk)
        writer.write(struct.pack(">I", 0))
        await writer.drain()
        response = (await asyncio.wait_for(reader.read(4096), timeout=30)).decode(
            "utf-8", errors="replace"
        )
        writer.close()
        await writer.wait_closed()
    except UploadSecurityError:
        raise
    except Exception as exc:
        if settings.CLAMAV_REQUIRED:
            raise UploadSecurityError(
                "Антивирусная проверка временно недоступна", status_code=503
            ) from exc
        return
    if "FOUND" in response:
        raise UploadSecurityError("Файл отклонён антивирусом")
    if "OK" not in response and settings.CLAMAV_REQUIRED:
        raise UploadSecurityError("Антивирус не подтвердил безопасность файла", status_code=503)


async def secure_upload(file: UploadFile) -> tuple[str, bytes]:
    filename = sanitize_filename(file.filename)
    data = await read_limited_upload(file)
    validate_file_signature(filename, data)
    await scan_for_malware(data)
    return filename, data
