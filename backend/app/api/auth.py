"""Authentication, rotating sessions, MFA and password recovery."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.security import (
    create_access_token,
    create_upload_token,
    decrypt_secret,
    encrypt_secret,
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    new_totp_secret,
    totp_uri,
    validate_password,
    verify_password,
    verify_totp,
)
from app.db.base import get_db
from app.db.models import PasswordResetToken, RefreshSession, Role, User
from app.db.schemas import UserOut
from app.services.email import email_enabled, send_email
from app.services.rate_limit import enforce_limit
from app.utils.audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    full_name: str | None = Field(default=None, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=10, max_length=128)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=6)


def _client_ip(request: Request) -> str | None:
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-real-ip")
        or (request.client.host if request.client else None)
    )


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.AUTH_COOKIE_NAME,
        token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        domain=settings.COOKIE_DOMAIN,
        path="/api/auth",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(
        settings.AUTH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/api/auth",
    )


async def _create_session(
    db: AsyncSession, user: User, request: Request, response: Response
) -> LoginResponse:
    access = create_access_token({"sub": str(user.id)})
    refresh = new_opaque_token()
    db.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hash_opaque_token(refresh),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=request.headers.get("user-agent", "")[:512] or None,
            ip_address=_client_ip(request),
        )
    )
    _set_auth_cookie(response, access)
    _set_refresh_cookie(response, refresh)
    return LoginResponse(
        access_token=access,
        user_id=str(user.id),
        role=user.role,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request) or "unknown"
    await enforce_limit(f"auth:login:{ip}", limit=10, window_seconds=15 * 60)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user.mfa_enabled:
        secret = decrypt_secret(user.mfa_secret_encrypted or "")
        if not secret or not data.mfa_code or not verify_totp(secret, data.mfa_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA code required or invalid",
            )

    login_response = await _create_session(db, user, request, response)
    await log_action(
        db,
        action="user_login",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return login_response


@router.post("/refresh", response_model=LoginResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=401, detail="Refresh session not found")

    now = datetime.now(timezone.utc)
    session = (
        await db.execute(
            select(RefreshSession)
            .where(RefreshSession.token_hash == hash_opaque_token(raw))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        _clear_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh session expired")

    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        _clear_cookies(response)
        raise HTTPException(status_code=401, detail="User not found or inactive")

    session.revoked_at = now
    result = await _create_session(db, user, request, response)
    await db.commit()
    return result


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw:
        await db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_hash == hash_opaque_token(raw),
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
    _clear_cookies(response)


@router.post("/upload-token")
async def upload_token(user: User = Depends(get_current_user)):
    """Five-minute token accepted only by file-upload endpoints."""
    return {"upload_token": create_upload_token(str(user.id)), "expires_in": 300}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request) or "unknown"
    await enforce_limit(f"auth:register:{ip}", limit=5, window_seconds=60 * 60)
    try:
        validate_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await db.execute(
        select(User).where(
            (User.email == data.email) | (User.username == data.username)
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email or username already exists",
        )

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=Role.LAWYER.value,
    )
    db.add(user)
    await db.flush()
    await log_action(
        db,
        action="user_registered",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/password/forgot")
async def forgot_password(
    data: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not email_enabled():
        raise HTTPException(status_code=503, detail="Восстановление пароля временно недоступно")
    await enforce_limit(
        f"auth:forgot:{_client_ip(request) or 'unknown'}",
        limit=5,
        window_seconds=60 * 60,
    )
    user = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if user and user.is_active:
        raw = new_opaque_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_opaque_token(raw),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
        await db.commit()
        link = f"{settings.PUBLIC_APP_URL.rstrip('/')}/reset-password?token={raw}"
        await send_email(
            user.email,
            "Восстановление пароля",
            f"Ссылка действует 30 минут:\n{link}\n\nЕсли вы не запрашивали сброс, проигнорируйте письмо.",
        )
    return {"detail": "Если аккаунт существует, письмо отправлено"}


@router.post("/password/reset")
async def reset_password(
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    try:
        validate_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    token = (
        await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == hash_opaque_token(data.token))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или истекла")
    user = await db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна")
    user.hashed_password = hash_password(data.password)
    token.used_at = now
    await db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()
    return {"detail": "Пароль изменён"}


@router.post("/mfa/setup")
async def setup_mfa(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    secret = new_totp_secret()
    user.mfa_secret_encrypted = encrypt_secret(secret)
    user.mfa_enabled = False
    await db.commit()
    return {"secret": secret, "otpauth_uri": totp_uri(secret, user.email)}


@router.post("/mfa/enable")
async def enable_mfa(
    data: MfaCodeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = decrypt_secret(user.mfa_secret_encrypted or "")
    if not secret or not verify_totp(secret, data.code):
        raise HTTPException(status_code=400, detail="Неверный код MFA")
    user.mfa_enabled = True
    await db.commit()
    return {"detail": "MFA включена"}


@router.post("/mfa/disable")
async def disable_mfa(
    data: MfaDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = decrypt_secret(user.mfa_secret_encrypted or "")
    if (
        not verify_password(data.password, user.hashed_password)
        or not secret
        or not verify_totp(secret, data.code)
    ):
        raise HTTPException(status_code=400, detail="Пароль или код MFA неверны")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    await db.commit()
    return {"detail": "MFA отключена"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
