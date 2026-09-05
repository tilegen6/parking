"""Tariff Service — тарифы и расчёт стоимости парковки (ТЗ §3.4)."""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models import Tariff
from src.schemas import TariffCreate, TariffOut, TariffUpdate


def calculate_price(
    duration_seconds: int,
    *,
    free_minutes: int,
    price_per_hour: float,
    daily_cap: float | None,
) -> float:
    """Стоимость парковки по тарифу (ТЗ §3.4).

    - Первые ``free_minutes`` — бесплатно.
    - Далее почасовая оплата с округлением вверх (ceil).
    - ``daily_cap`` — максимум за сутки (24ч): применяется на каждые полные
      сутки (для многодневной стоянки умножается). ``None`` → без ограничения.
    """
    duration_minutes = duration_seconds / 60
    billable_minutes = duration_minutes - free_minutes
    if billable_minutes <= 0:
        return 0.0

    day_minutes = 24 * 60
    full_days = int(billable_minutes // day_minutes)
    rem_minutes = billable_minutes - full_days * day_minutes
    rem_hours = math.ceil(rem_minutes / 60)

    def day_cost(hours: float) -> float:
        cost = hours * price_per_hour
        return min(cost, daily_cap) if daily_cap is not None else cost

    total = full_days * day_cost(24) + day_cost(rem_hours)
    return round(total, 2)


def tariff_price(duration_seconds: int, tariff: Tariff | None) -> float:
    """Стоимость сессии по объекту тарифа (обёртка над calculate_price)."""
    if tariff is None:
        return 0.0
    return calculate_price(
        duration_seconds,
        free_minutes=tariff.free_minutes,
        price_per_hour=tariff.price_per_hour,
        daily_cap=tariff.daily_cap,
    )


async def get_active_tariff(session: AsyncSession) -> Tariff | None:
    """Активный тариф (для расчёта стоимости сессии). Последний is_active."""
    result = await session.execute(
        select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.id.desc())
    )
    return result.scalars().first()


# --------------------------------------------------------------------------- #
# HTTP API — CRUD тарифов (задачи Backend: GET/POST/PUT/DELETE /tariffs)
# --------------------------------------------------------------------------- #

router = APIRouter(prefix="/api/v1", tags=["tariffs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/tariffs", response_model=list[TariffOut])
async def list_tariffs(session: SessionDep) -> list[TariffOut]:
    """Список тарифов."""
    result = await session.execute(select(Tariff).order_by(Tariff.id))
    return [TariffOut.model_validate(t) for t in result.scalars().all()]


@router.post("/tariffs", response_model=TariffOut, status_code=201)
async def create_tariff(payload: TariffCreate, session: SessionDep) -> TariffOut:
    """Создать тариф."""
    tariff = Tariff(**payload.model_dump())
    session.add(tariff)
    await session.flush()
    await session.refresh(tariff)
    return TariffOut.model_validate(tariff)


@router.get("/tariffs/{tariff_id}", response_model=TariffOut)
async def get_tariff(tariff_id: int, session: SessionDep) -> TariffOut:
    """Один тариф по id."""
    tariff = await session.get(Tariff, tariff_id)
    if tariff is None:
        raise HTTPException(status_code=404, detail="Тариф не найден")
    return TariffOut.model_validate(tariff)


@router.put("/tariffs/{tariff_id}", response_model=TariffOut)
async def update_tariff(
    tariff_id: int, payload: TariffUpdate, session: SessionDep
) -> TariffOut:
    """Обновить тариф (частично — только переданные поля)."""
    tariff = await session.get(Tariff, tariff_id)
    if tariff is None:
        raise HTTPException(status_code=404, detail="Тариф не найден")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tariff, field, value)
    await session.flush()
    await session.refresh(tariff)
    return TariffOut.model_validate(tariff)


@router.delete("/tariffs/{tariff_id}", status_code=204)
async def delete_tariff(tariff_id: int, session: SessionDep) -> None:
    """Удалить тариф."""
    tariff = await session.get(Tariff, tariff_id)
    if tariff is None:
        raise HTTPException(status_code=404, detail="Тариф не найден")
    await session.delete(tariff)
