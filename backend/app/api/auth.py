"""Auth-эндпоинты: логин, регистрация, текущий пользователь.

Каркас Week 1-2; полная реализация с организациями — Weeks 3-4 (Task 1.6).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.base import get_db
from app.db.models import Role, User
from app.db.schemas import UserOut
from app.utils.audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    access_token = create_access_token(data={"sub": user.email})

    await log_action(
        db,
        action="user_login",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return LoginResponse(
        access_token=access_token, user_id=str(user.id), role=user.role
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)
):
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
        role=Role.LAWYER.value,  # Роль по умолчанию
    )
    db.add(user)
    await db.flush()

    await log_action(
        db,
        action="user_registered",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
