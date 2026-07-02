"""Session Service — парковочные сессии поверх событий распознавания.

Логика по ТЗ «Smart Parking ANPR» v1.0 (§3.3, §4.2, §6.2):

  * Гейт по confidence: confidence < порога или пустой номер → событие помечается
    low_confidence, сессия НЕ создаётся (на ручную проверку в admin). (§2.4, §6.2)
  * ENTRY: есть активная сессия по номеру → обновить last_seen, новую не создавать
    (дубль/повторный въезд, §6.2); иначе — создать сессию status=active.
  * EXIT: есть активная сессия → закрыть (exit_time, duration, status=unpaid);
    нет — повтор выезда в окне дедупа игнорируем, иначе помечаем событие
    event_without_session и уведомляем admin (§6.2).

Сервис работает с НОРМАЛИЗОВАННЫМ событием (см. cv/contract/), не зная про Hikvision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_session
from src.models import (
    Direction,
    EventFlag,
    ParkingSession,
    RecognitionEvent,
    SessionStatus,
)
from src.schemas import PaginatedSessions, ParkingSessionOut

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    """Результат обработки события (для логов/ответа эндпоинта)."""

    action: str  # created | updated_last_seen | closed | event_without_session
    #              | low_confidence | duplicate_exit | ignored
    session_id: int | None = None
    detail: str = ""


async def find_active_session(
    session: AsyncSession, plate: str
) -> ParkingSession | None:
    """Активная (открытая) сессия по номеру, если есть."""
    result = await session.execute(
        select(ParkingSession)
        .where(
            ParkingSession.plate_number == plate,
            ParkingSession.status == SessionStatus.ACTIVE,
        )
        .order_by(ParkingSession.entry_time.desc())
    )
    return result.scalars().first()


def _as_aware(dt: datetime | None) -> datetime | None:
    """Привести datetime к tz-aware (UTC), если он наивный.

    Защита от смешения наивных/aware дат (разные источники, разные СУБД),
    иначе вычитание datetime бросает TypeError.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_low_confidence(event: RecognitionEvent) -> bool:
    if not event.plate_number:
        return True
    if (
        event.confidence is not None
        and event.confidence < settings.recognition_min_confidence
    ):
        return True
    return False


async def _recently_closed(
    session: AsyncSession, plate: str, when: object
) -> ParkingSession | None:
    """Недавно закрытая сессия (для гашения повторного EXIT в окне дедупа)."""
    window = timedelta(seconds=settings.session_dedup_window_seconds)
    result = await session.execute(
        select(ParkingSession)
        .where(
            ParkingSession.plate_number == plate,
            ParkingSession.exit_time.is_not(None),
            ParkingSession.exit_time >= when - window,  # type: ignore[operator]
        )
        .order_by(ParkingSession.exit_time.desc())
    )
    return result.scalars().first()


async def handle_recognition_event(
    session: AsyncSession, event: RecognitionEvent
) -> SessionResult:
    """Точка входа: применить событие к парковочным сессиям."""
    if _is_low_confidence(event):
        event.flag = EventFlag.LOW_CONFIDENCE
        logger.info(
            "low_confidence: номер=%s conf=%s → ручная проверка",
            event.plate_number,
            event.confidence,
        )
        return SessionResult("low_confidence")

    if event.direction == Direction.ENTRY:
        return await _handle_entry(session, event)
    if event.direction == Direction.EXIT:
        return await _handle_exit(session, event)

    logger.info("direction=UNKNOWN для %s — сессии не трогаем", event.plate_number)
    return SessionResult("ignored", detail="direction=UNKNOWN")


async def _handle_entry(
    session: AsyncSession, event: RecognitionEvent
) -> SessionResult:
    active = await find_active_session(session, event.plate_number)  # type: ignore[arg-type]
    if active is not None:
        # Дубль / повторный въезд (ТЗ §6.2): новую не создаём, освежаем last_seen
        active.last_seen = event.event_time
        logger.info("ENTRY дубль: %s → обновлён last_seen", event.plate_number)
        return SessionResult("updated_last_seen", active.id)

    parking = ParkingSession(
        plate_number=event.plate_number,
        status=SessionStatus.ACTIVE,
        entry_time=event.event_time,
        last_seen=event.event_time,
        entry_event_id=event.id,
        entry_camera_id=event.camera_id,
    )
    session.add(parking)
    await session.flush()
    logger.info("ENTRY: открыта сессия #%s для %s", parking.id, event.plate_number)
    return SessionResult("created", parking.id)


async def _handle_exit(
    session: AsyncSession, event: RecognitionEvent
) -> SessionResult:
    active = await find_active_session(session, event.plate_number)  # type: ignore[arg-type]

    if active is None:
        # Возможно, это повторный EXIT по уже закрытой сессии — гасим в окне дедупа
        recent = await _recently_closed(session, event.plate_number, event.event_time)  # type: ignore[arg-type]
        if recent is not None:
            recent.last_seen = event.event_time
            logger.info("EXIT дубль: %s → игнор", event.plate_number)
            return SessionResult("duplicate_exit", recent.id)

        # Выезд без активной сессии (ТЗ §6.2)
        event.flag = EventFlag.EVENT_WITHOUT_SESSION
        logger.warning(
            "event_without_session: выезд %s без активной сессии — уведомить admin",
            event.plate_number,
        )
        return SessionResult("event_without_session")

    active.exit_time = event.event_time
    active.last_seen = event.event_time
    active.exit_event_id = event.id
    active.exit_camera_id = event.camera_id
    active.status = SessionStatus.UNPAID  # MVP v1 без оплаты (ТЗ §4.2)
    entry = _as_aware(active.entry_time)
    exit_at = _as_aware(event.event_time)
    if entry is not None and exit_at is not None:
        active.duration_seconds = int((exit_at - entry).total_seconds())
    logger.info(
        "EXIT: закрыта сессия #%s (%s сек) для %s",
        active.id,
        active.duration_seconds,
        event.plate_number,
    )
    return SessionResult("closed", active.id)


# --------------------------------------------------------------------------- #
# HTTP API (задачи Backend #8–14)
# --------------------------------------------------------------------------- #

router = APIRouter(prefix="/api/v1", tags=["parking-sessions"])

# Разрешённые поля сортировки (whitelist — защита от инъекций в order_by)
_SORT_FIELDS = {
    "entry_time": ParkingSession.entry_time,
    "exit_time": ParkingSession.exit_time,
    "duration_seconds": ParkingSession.duration_seconds,
    "plate_number": ParkingSession.plate_number,
}


def _to_out(row: ParkingSession) -> ParkingSessionOut:
    """Сериализовать сессию + посчитать parked_seconds (время стоянки)."""
    out = ParkingSessionOut.model_validate(row)
    if row.status == SessionStatus.ACTIVE and row.entry_time is not None:
        entry = _as_aware(row.entry_time)
        now = datetime.now(timezone.utc)
        out.parked_seconds = int((now - entry).total_seconds())  # type: ignore[operator]
    else:
        out.parked_seconds = row.duration_seconds
    return out


@router.get("/parking-sessions", response_model=PaginatedSessions)
async def list_sessions(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    plate: str | None = Query(None, description="Поиск по номеру (частичное совпадение)"),
    status: str | None = Query(None, description="active / unpaid / paid / cancelled / whitelist"),
    date_from: date | None = Query(None, description="Фильтр по дате въезда (с)"),
    date_to: date | None = Query(None, description="Фильтр по дате въезда (по)"),
    sort: str = Query("entry_time", description="Поле сортировки"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedSessions:
    """Список парковочных сессий с фильтрами, сортировкой и пагинацией."""
    conditions: list[ColumnElement[bool]] = []
    if plate:
        conditions.append(ParkingSession.plate_number.ilike(f"%{plate}%"))
    if status:
        conditions.append(ParkingSession.status == status.lower())
    if date_from:
        conditions.append(
            ParkingSession.entry_time
            >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to:
        conditions.append(
            ParkingSession.entry_time
            <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        )

    base = select(ParkingSession)
    for cond in conditions:
        base = base.where(cond)

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    sort_col = _SORT_FIELDS.get(sort, ParkingSession.entry_time)
    sort_col = sort_col.asc() if order == "asc" else sort_col.desc()

    rows = (
        (
            await session.execute(
                base.order_by(sort_col).offset((page - 1) * limit).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    pages = (total + limit - 1) // limit if total else 0
    return PaginatedSessions(
        items=[_to_out(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@router.get("/parking-sessions/active", response_model=list[ParkingSessionOut])
async def list_active_sessions(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ParkingSessionOut]:
    """Активные сессии (машины сейчас на парковке)."""
    rows = (
        (
            await session.execute(
                select(ParkingSession)
                .where(ParkingSession.status == SessionStatus.ACTIVE)
                .order_by(ParkingSession.entry_time.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_out(r) for r in rows]


@router.get("/parking-sessions/{session_id}", response_model=ParkingSessionOut)
async def get_parking_session(
    session_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ParkingSessionOut:
    """Одна парковочная сессия по id."""
    row = await session.get(ParkingSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return _to_out(row)
