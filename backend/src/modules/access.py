"""Списки доступа (зелёный/жёлтый/красный) + оповещения (итерация 3).

Резолвер решает судьбу номера на шлагбауме, CRUD ведут пользователи с правами
(list_manager/admin) с записью в аудит. Красный список создаёт Alert.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models import AccessEntry, AccessListType, Alert, User, UserRole
from src.modules.auth import get_current_user, record_audit, require_role
from src.schemas import (
    AccessEntryCreate,
    AccessEntryOut,
    AccessEntryUpdate,
    AlertOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["access-lists"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ManagerDep = Annotated[User, Depends(require_role(UserRole.LIST_MANAGER))]
AuthedDep = Annotated[User, Depends(get_current_user)]

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
# Красный важнее зелёного важнее жёлтого при конфликте на одном уровне
_PRIORITY = {AccessListType.RED: 3, AccessListType.GREEN: 2, AccessListType.YELLOW: 1}

# Казахстанские номера набираются кириллицей, но на знаке — буквы, визуально
# совпадающие с латиницей. Разные камеры/прошивки отдают номер то так, то так
# («777АВС02» кириллицей vs «777ABC02» латиницей). Без приведения к одному
# алфавиту одна и та же машина на въезде и выезде считается разной, а чистая
# кириллица вообще вырезалась бы `_NON_ALNUM` в пустую строку. Транслитерируем
# гомоглифы к латинице ДО очистки.
_CYRILLIC_TO_LATIN = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "У": "Y",
        "Х": "X",
    }
)


def normalize_plate(plate: str | None) -> str:
    """Номер к каноничному виду: верхний регистр, латиница, только буквы/цифры.

    Единая точка канонизации для всего: списки доступа, поиск активной сессии,
    lookup Kaspi. Номер нормализуется один раз на приёме события и дальше везде
    сравнивается уже канонический.
    """
    upper = (plate or "").upper().translate(_CYRILLIC_TO_LATIN)
    return _NON_ALNUM.sub("", upper)


async def resolve_access(
    session: AsyncSession, plate: str | None, gate_id: int | None
) -> AccessEntry | None:
    """Эффективная запись списка для номера на шлагбауме.

    Учитываются записи данного шлагбаума и глобальные (gate_id IS NULL).
    Приоритет: запись на конкретный шлагбаум > глобальная; при равенстве —
    красный > зелёный > жёлтый.
    """
    norm = normalize_plate(plate)
    if not norm:
        return None
    conds = [AccessEntry.plate == norm, AccessEntry.is_active.is_(True)]
    if gate_id is None:
        conds.append(AccessEntry.gate_id.is_(None))
    else:
        conds.append(or_(AccessEntry.gate_id == gate_id, AccessEntry.gate_id.is_(None)))
    rows = (await session.execute(select(AccessEntry).where(*conds))).scalars().all()
    if not rows:
        return None

    def _key(e: AccessEntry) -> tuple[int, int]:
        specific = 1 if e.gate_id is not None else 0
        return (specific, _PRIORITY.get(e.list_type, 0))

    return max(rows, key=_key)


async def record_alert(
    session: AsyncSession,
    kind: str,
    *,
    plate: str | None = None,
    gate_id: int | None = None,
    message: str | None = None,
) -> None:
    """Создать оповещение ответственному (напр. по красному списку)."""
    session.add(Alert(kind=kind, plate=plate, gate_id=gate_id, message=message))


# --- CRUD списков (list_manager / admin) ---
@router.get("/access-entries", response_model=list[AccessEntryOut])
async def list_entries(
    session: SessionDep,
    _: AuthedDep,
    list_type: str | None = Query(None),
    gate_id: int | None = Query(None),
    plate: str | None = Query(None),
) -> list[AccessEntryOut]:
    stmt = select(AccessEntry).order_by(AccessEntry.id.desc())
    if list_type:
        stmt = stmt.where(AccessEntry.list_type == list_type)
    if gate_id is not None:
        stmt = stmt.where(AccessEntry.gate_id == gate_id)
    if plate:
        stmt = stmt.where(AccessEntry.plate.ilike(f"%{normalize_plate(plate)}%"))
    rows = (await session.execute(stmt)).scalars().all()
    return [AccessEntryOut.model_validate(e) for e in rows]


@router.post("/access-entries", response_model=AccessEntryOut, status_code=201)
async def create_entry(
    payload: AccessEntryCreate, session: SessionDep, user: ManagerDep
) -> AccessEntryOut:
    if payload.list_type not in AccessListType.ALL:
        raise HTTPException(400, f"list_type: {', '.join(AccessListType.ALL)}")
    entry = AccessEntry(
        plate=normalize_plate(payload.plate),
        list_type=payload.list_type,
        gate_id=payload.gate_id,
        valid_until=payload.valid_until,
        note=payload.note,
        is_active=payload.is_active,
        created_by_id=user.id,
        created_by_username=user.username,
    )
    session.add(entry)
    await session.flush()
    await record_audit(
        session,
        user,
        "access.create",
        entity="access_entry",
        entity_id=entry.id,
        detail=f"{entry.plate} → {entry.list_type} (gate={entry.gate_id})",
    )
    await session.refresh(entry)
    return AccessEntryOut.model_validate(entry)


@router.put("/access-entries/{entry_id}", response_model=AccessEntryOut)
async def update_entry(
    entry_id: int, payload: AccessEntryUpdate, session: SessionDep, user: ManagerDep
) -> AccessEntryOut:
    entry = await session.get(AccessEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Запись не найдена")
    data = payload.model_dump(exclude_unset=True)
    if "list_type" in data and data["list_type"] not in AccessListType.ALL:
        raise HTTPException(400, f"list_type: {', '.join(AccessListType.ALL)}")
    for field, value in data.items():
        setattr(entry, field, value)
    await session.flush()
    await record_audit(
        session,
        user,
        "access.update",
        entity="access_entry",
        entity_id=entry.id,
        detail=",".join(sorted(data)),
    )
    await session.refresh(entry)
    return AccessEntryOut.model_validate(entry)


@router.delete("/access-entries/{entry_id}", status_code=204)
async def delete_entry(entry_id: int, session: SessionDep, user: ManagerDep) -> None:
    entry = await session.get(AccessEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Запись не найдена")
    await record_audit(
        session,
        user,
        "access.delete",
        entity="access_entry",
        entity_id=entry.id,
        detail=f"{entry.plate} ({entry.list_type})",
    )
    await session.delete(entry)


# --- Оповещения (красный список) ---
@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    session: SessionDep,
    _: AuthedDep,
    only_new: bool = Query(True, description="только неподтверждённые"),
) -> list[AlertOut]:
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(100)
    if only_new:
        stmt = stmt.where(Alert.acknowledged.is_(False))
    rows = (await session.execute(stmt)).scalars().all()
    return [AlertOut.model_validate(a) for a in rows]


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def ack_alert(alert_id: int, session: SessionDep, _: AuthedDep) -> AlertOut:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Оповещение не найдено")
    alert.acknowledged = True
    await session.flush()
    await session.refresh(alert)
    return AlertOut.model_validate(alert)
