"""Файловое хранилище MinIO (S3-совместимое)."""

import asyncio
import mimetypes
import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

_client = None


def get_s3():
    global _client
    if _client is None:
        scheme = "https" if settings.MINIO_SECURE else "http"
        _client = boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{settings.MINIO_ENDPOINT}",
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
    return _client


def ensure_bucket() -> None:
    s3 = get_s3()
    try:
        s3.head_bucket(Bucket=settings.MINIO_BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=settings.MINIO_BUCKET)


def upload_file(data: bytes, filename: str, org_id: uuid.UUID) -> str:
    """Кладёт файл в бакет, возвращает ключ (file_path контракта)."""
    ensure_bucket()
    key = f"{org_id}/{uuid.uuid4()}/{filename}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    get_s3().put_object(
        Bucket=settings.MINIO_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


async def upload_file_async(data: bytes, filename: str, org_id: uuid.UUID) -> str:
    return await asyncio.to_thread(upload_file, data, filename, org_id)


def presigned_download_url(key: str, expires_seconds: int = 3600) -> str:
    return get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.MINIO_BUCKET, "Key": key},
        ExpiresIn=expires_seconds,
    )


def open_download_stream(key: str):
    """Открывает объект MinIO для отдачи наружу через бэкенд.

    Возвращает (тело, content_type, размер|None). Тело — botocore
    StreamingBody: читать чанками через ``.iter_chunks()``, в конце ``.close()``.
    Так файл идёт браузеру через api-домен, а MinIO остаётся во внутренней сети
    (presigned-ссылка вела бы на недоступный `minio:9000`).
    """
    obj = get_s3().get_object(Bucket=settings.MINIO_BUCKET, Key=key)
    return (
        obj["Body"],
        obj.get("ContentType") or "application/octet-stream",
        obj.get("ContentLength"),
    )
