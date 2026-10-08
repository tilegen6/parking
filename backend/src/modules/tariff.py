"""Tariff Service — тарифы и расчёт стоимости парковки (ТЗ §3.4)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models import AccessType, ParkingSession, Tariff
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


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def price_for_session(
    parking: ParkingSession, tariff: Tariff | None, ref_time: datetime
) -> float:
    """Цена сессии на момент ref_time с учётом списка доступа (green/yellow).

    ЕДИНАЯ точка расчёта — зовётся и при выезде (_handle_exit), и при запросе
    долга (amount_due/Kaspi), иначе с бесплатных машин берут реальные деньги.

    - GREEN — всегда бесплатно;
    - YELLOW — бесплатно до free_until, далее тариф на «перебор»; но платное
      время считаем от max(entry, free_until), а не от free_until: иначе
      просроченный жёлтый пропуск (free_until в прошлом) даёт счёт за десятки
      часов до въезда. YELLOW без free_until = обычная платная (не «бесплатно
      навсегда»);
    - иначе — обычный тариф за фактическую стоянку.

    Длительность клампится в неотрицательную: сбитые часы камеры (event_time в
    прошлом/будущем) не должны давать отрицательный счёт.
    """
    entry = _aware(parking.entry_time)
    ref = _aware(ref_time)
    if entry is None or ref is None:
        return 0.0
    duration = max(0, int((ref - entry).total_seconds()))

    if parking.access_type == AccessType.GREEN:
        return 0.0
    if parking.access_type == AccessType.YELLOW:
        free_until = _aware(parking.free_until)
        if free_until is None:
            return tariff_price(duration, tariff)
        billable_start = max(entry, free_until)
        billable = max(0, int((ref - billable_start).total_seconds()))
        return tariff_price(billable, tariff)
    return tariff_price(duration, tariff)


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


async def _deactivate_other_tariffs(session: AsyncSession, keep_id: int | None) -> None:
    """Активным может быть только один тариф — снимаем флаг с остальных.

    Иначе бэкенд берёт последний по id, фронт — первый, и показанная сумма не
    совпадает с фактически выставленной.
    """
    stmt = select(Tariff).where(Tariff.is_active.is_(True))
    if keep_id is not None:
        stmt = stmt.where(Tariff.id != keep_id)
    for other in (await session.execute(stmt)).scalars().all():
        other.is_active = False


@router.post("/tariffs", response_model=TariffOut, status_code=201)
async def create_tariff(payload: TariffCreate, session: SessionDep) -> TariffOut:
    """Создать тариф. Если он активный — остальные деактивируются."""
    # Снимаем флаг с прочих ДО вставки: иначе на миг активных двое и уникальный
    # индекс отвергнет INSERT.
    if payload.is_active:
        await _deactivate_other_tariffs(session, None)
        await session.flush()
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
    data = payload.model_dump(exclude_unset=True)
    # Если этот тариф становится (или остаётся) активным — сперва гасим прочие,
    # иначе уникальный индекс «один активный» отвергнет UPDATE.
    if data.get("is_active", tariff.is_active):
        await _deactivate_other_tariffs(session, tariff.id)
        await session.flush()
    for field, value in data.items():
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
