"""Управление пользователями и просмотр аудита (только роль admin)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models import AuditLog, User, UserRole
from src.modules.auth import hash_password, record_audit, require_role
from src.schemas import AuditLogOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/v1", tags=["users"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Все ручки — только для админа
AdminDep = Annotated[User, Depends(require_role(UserRole.ADMIN))]


@router.get("/users", response_model=list[UserOut])
async def list_users(session: SessionDep, _: AdminDep) -> list[UserOut]:
    rows = (await session.execute(select(User).order_by(User.id))).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserCreate, session: SessionDep, admin: AdminDep
) -> UserOut:
    if payload.role not in UserRole.ALL:
        raise HTTPException(400, f"роль: {', '.join(UserRole.ALL)}")
    exists = (
        await session.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(409, "Пользователь с таким логином уже есть")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
    )
    session.add(user)
    await session.flush()
    await record_audit(
        session,
        admin,
        "user.create",
        entity="user",
        entity_id=user.id,
        detail=f"{user.username} ({user.role})",
    )
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, payload: UserUpdate, session: SessionDep, admin: AdminDep
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Пользователь не найден")
    data = payload.model_dump(exclude_unset=True)
    if "role" in data and data["role"] not in UserRole.ALL:
        raise HTTPException(400, f"роль: {', '.join(UserRole.ALL)}")
    # Нельзя снять с себя доступ / понизить последнего активного админа
    if user.id == admin.id and (data.get("is_active") is False or data.get("role")):
        raise HTTPException(400, "Нельзя менять роль/активность своей учётки")
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(user, field, value)
    await session.flush()
    await record_audit(
        session,
        admin,
        "user.update",
        entity="user",
        entity_id=user.id,
        detail=",".join(sorted(payload.model_dump(exclude_unset=True))),
    )
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.get("/audit-log", response_model=list[AuditLogOut])
async def list_audit(
    session: SessionDep,
    _: AdminDep,
    limit: int = Query(100, ge=1, le=500),
) -> list[AuditLogOut]:
    rows = (
        (
            await session.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [AuditLogOut.model_validate(a) for a in rows]
