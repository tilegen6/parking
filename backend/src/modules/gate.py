"""Gate Service — шлагбаумы/зоны (итерация 1).

Фундамент под списки доступа и шлагбаум 2-го уровня: камеры и сессии
привязываются к шлагбауму, учёт раздельный по зонам.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models import Gate
from src.schemas import GateCreate, GateOut, GateUpdate

router = APIRouter(prefix="/api/v1", tags=["gates"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_default_gate(session: AsyncSession) -> Gate | None:
    """Первый активный шлагбаум (для мест, где зона явно не указана)."""
    result = await session.execute(
        select(Gate).where(Gate.is_active.is_(True)).order_by(Gate.level, Gate.id)
    )
    return result.scalars().first()


@router.get("/gates", response_model=list[GateOut])
async def list_gates(session: SessionDep) -> list[GateOut]:
    """Список шлагбаумов."""
    result = await session.execute(select(Gate).order_by(Gate.level, Gate.id))
    return [GateOut.model_validate(g) for g in result.scalars().all()]


@router.post("/gates", response_model=GateOut, status_code=201)
async def create_gate(payload: GateCreate, session: SessionDep) -> GateOut:
    """Создать шлагбаум."""
    gate = Gate(**payload.model_dump())
    session.add(gate)
    await session.flush()
    await session.refresh(gate)
    return GateOut.model_validate(gate)


@router.get("/gates/{gate_id}", response_model=GateOut)
async def get_gate(gate_id: int, session: SessionDep) -> GateOut:
    """Один шлагбаум по id."""
    gate = await session.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail="Шлагбаум не найден")
    return GateOut.model_validate(gate)


@router.put("/gates/{gate_id}", response_model=GateOut)
async def update_gate(
    gate_id: int, payload: GateUpdate, session: SessionDep
) -> GateOut:
    """Обновить шлагбаум (частично — только переданные поля)."""
    gate = await session.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail="Шлагбаум не найден")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(gate, field, value)
    await session.flush()
    await session.refresh(gate)
    return GateOut.model_validate(gate)


@router.delete("/gates/{gate_id}", status_code=204)
async def delete_gate(gate_id: int, session: SessionDep) -> None:
    """Удалить шлагбаум (камеры/сессии остаются, gate_id → NULL)."""
    gate = await session.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail="Шлагбаум не найден")
    await session.delete(gate)
