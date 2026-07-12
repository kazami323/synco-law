import uuid

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, decode_upload_token
from app.core.config import settings
from app.db.base import get_db
from app.db.models import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    auth_cookie: str | None = Cookie(default=None, alias=settings.AUTH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials is not None else auth_cookie
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    payload = decode_access_token(token)
    if payload is None or payload.get("sub") is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    subject = str(payload["sub"])
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        user_id = None
    query = select(User).where(User.id == user_id) if user_id else select(User).where(User.email == subject)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )
    return user


async def get_upload_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    auth_cookie: str | None = Cookie(default=None, alias=settings.AUTH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials is not None else auth_cookie
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_upload_token(token) or decode_access_token(token)
    if payload is None or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid upload token")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid upload token") from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
