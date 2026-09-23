"""Аутентификация: пароли (bcrypt), JWT, зависимости ролей, аудит.

Итерация 2: «список ведут пользователи с правами, действия с привязкой к
личности». Здесь — вход, проверка токена, гварды по ролям и запись аудита.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_session
from src.models import AuditLog, User, UserRole
from src.schemas import LoginRequest, TokenResponse, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# bcrypt ограничен 72 байтами — длинные пароли усечём (стандартная практика)
_BCRYPT_MAX = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:_BCRYPT_MAX], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:_BCRYPT_MAX], hashed.encode())
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> dict[str, object]:
    return jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )


async def authenticate(
    session: AsyncSession, username: str, password: str
) -> User | None:
    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None


# --- Зависимости FastAPI ---
_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: SessionDep,
) -> User:
    """Пользователь из Bearer-токена; 401 при невалидном/отключённом."""
    try:
        payload = decode_token(creds.credentials)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Недействительный токен"
        ) from e
    user = await session.get(User, int(str(payload.get("sub") or 0)))
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Пользователь не найден или отключён"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: str) -> Callable[..., Awaitable[User]]:
    """Гвард по ролям. Админ проходит всегда."""

    async def _dep(user: CurrentUser) -> User:
        if roles and user.role != UserRole.ADMIN and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return _dep


async def record_audit(
    session: AsyncSession,
    user: User | None,
    action: str,
    *,
    entity: str | None = None,
    entity_id: object | None = None,
    detail: str | None = None,
) -> None:
    """Записать действие пользователя в журнал аудита (кто/что/когда)."""
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            detail=detail,
        )
    )


async def ensure_default_admin(session: AsyncSession) -> None:
    """Создать стартового администратора при пустой таблице пользователей."""
    count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    if count:
        return
    session.add(
        User(
            username=settings.default_admin_username,
            password_hash=hash_password(settings.default_admin_password),
            full_name="Администратор",
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    logger.warning(
        "Создан стартовый администратор '%s' — смените пароль при первом входе!",
        settings.default_admin_username,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
    """Вход по логину/паролю — возвращает JWT и профиль."""
    user = await authenticate(session, body.username, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    return TokenResponse(
        access_token=create_access_token(user),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    """Текущий пользователь по токену."""
    return user
