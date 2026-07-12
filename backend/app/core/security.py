import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access", "jti": secrets.token_hex(12)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_upload_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode(
        {
            "sub": user_id,
            "exp": expire,
            "type": "upload",
            "jti": secrets.token_hex(12),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_access_token(token: str) -> dict | None:
    """Возвращает payload или None, если токен невалиден/просрочен."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload if payload.get("type", "access") == "access" else None
    except JWTError:
        return None


def decode_upload_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload if payload.get("type") == "upload" else None
    except JWTError:
        return None


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_password(password: str) -> None:
    if len(password) < 10:
        raise ValueError("Пароль должен содержать минимум 10 символов")
    if len(password) > 128:
        raise ValueError("Пароль слишком длинный")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ValueError("Пароль должен содержать буквы и цифры")


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, at: datetime | None = None) -> str:
    now = at or datetime.now(timezone.utc)
    counter = int(now.timestamp()) // 30
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str) -> bool:
    if not code.isdigit() or len(code) != 6:
        return False
    now = datetime.now(timezone.utc)
    return any(
        hmac.compare_digest(totp_code(secret, now + timedelta(seconds=offset)), code)
        for offset in (-30, 0, 30)
    )


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


def totp_uri(secret: str, email: str) -> str:
    issuer = settings.APP_NAME
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(email)}?"
        f"secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )
