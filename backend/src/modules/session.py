"""Session Service — парковочные сессии поверх событий распознавания.

Логика по ТЗ «Smart Parking ANPR» v1.0 (§3.3, §4.2, §6.2):

  * Гейт по confidence: confidence < порога или пустой номер → событие помечается
    low_confidence, сессия НЕ создаётся (на ручную проверку в admin). (§2.4, §6.2)
  * ENTRY: есть активная сессия по номеру → обновить last_seen, новую не создавать
    (дубль/повторный въезд, §6.2); иначе — создать сессию status=active.
  * EXIT: есть активная сессия → считаем стоимость за фактическое время; если
    оплачено < цены — ШЛАГБАУМ ЗАКРЫТ (сессия остаётся активной, нужна доплата),
    иначе выпускаем (exit_time, status=paid). Нет активной — повтор выезда в окне
    дедупа игнорируем, иначе event_without_session и уведомляем admin (§6.2).

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
from src.integrations.kaspi_autopay import KaspiAutoPayClient
from src.models import (
    AccessEntry,
    AccessListType,
    AccessType,
    AlertKind,
    Camera,
    Direction,
    EventFlag,
    ParkingSession,
    Payment,
    PaymentStatus,
    RecognitionEvent,
    SessionStatus,
)
from src.modules.access import normalize_plate, record_alert, resolve_access
from src.modules.tariff import get_active_tariff, tariff_price
from src.schemas import PaginatedSessions, ParkingSessionOut

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    """Результат обработки события (для логов/ответа эндпоинта)."""

    action: str  # created | entry_restarted | updated_last_seen | closed | ...
    #              | low_confidence | duplicate_exit | ignored
    session_id: int | None = None
    detail: str = ""


async def find_active_session(
    session: AsyncSession, plate: str
) -> ParkingSession | None:
    """Активная сессия по номеру на любом шлагбауме (для kaspi-автосписания)."""
    result = await session.execute(
        select(ParkingSession)
        .where(
            ParkingSession.plate_number == plate,
            ParkingSession.status == SessionStatus.ACTIVE,
        )
        .order_by(ParkingSession.entry_time.desc())
    )
    return result.scalars().first()


def _gate_cond(gate_id: int | None) -> ColumnElement[bool]:
    """Условие «та же зона»: конкретный шлагбаум или сессии без шлагбаума."""
    if gate_id is None:
        return ParkingSession.gate_id.is_(None)
    return ParkingSession.gate_id == gate_id


async def _resolve_gate_id(
    session: AsyncSession, event: RecognitionEvent
) -> int | None:
    """Шлагбаум события — из камеры (None, если камера не привязана/не найдена)."""
    if event.camera_id is None:
        return None
    result = await session.execute(
        select(Camera.gate_id).where(Camera.id == event.camera_id)
    )
    return result.scalar_one_or_none()


async def _find_active_at_gate(
    session: AsyncSession, plate: str, gate_id: int | None
) -> ParkingSession | None:
    """Активная сессия по номеру в пределах одного шлагбаума/зоны."""
    result = await session.execute(
        select(ParkingSession)
        .where(
            ParkingSession.plate_number == plate,
            ParkingSession.status == SessionStatus.ACTIVE,
            _gate_cond(gate_id),
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
    session: AsyncSession, plate: str, when: object, gate_id: int | None
) -> ParkingSession | None:
    """Недавно закрытая сессия на том же шлагбауме (гашение повторного EXIT)."""
    window = timedelta(seconds=settings.session_dedup_window_seconds)
    result = await session.execute(
        select(ParkingSession)
        .where(
            ParkingSession.plate_number == plate,
            ParkingSession.exit_time.is_not(None),
            ParkingSession.exit_time >= when - window,  # type: ignore[operator]
            _gate_cond(gate_id),
        )
        .order_by(ParkingSession.exit_time.desc())
    )
    return result.scalars().first()


def _differs_by_one_char(a: str, b: str) -> bool:
    """Ровно один отличающийся символ при равной длине (ТС-9: O↔0, I↔1 и т.п.)."""
    return len(a) == len(b) and sum(1 for x, y in zip(a, b) if x != y) == 1


async def _find_similar_active(
    session: AsyncSession, plate: str, gate_id: int | None
) -> ParkingSession | None:
    """Активная сессия на том же шлагбауме с номером ±1 символ (ТС-9).

    Возможная ошибка распознавания одного символа: не действуем автоматически,
    только помечаем possible_misread и отдаём на ручную проверку. Активных
    сессий немного (масштаб парковки) — линейный проход по ним допустим.
    """
    result = await session.execute(
        select(ParkingSession).where(
            ParkingSession.status == SessionStatus.ACTIVE,
            _gate_cond(gate_id),
        )
    )
    for s in result.scalars():
        if s.plate_number != plate and _differs_by_one_char(plate, s.plate_number):
            return s
    return None


async def _autopay_enter(session: AsyncSession, parking: ParkingSession) -> None:
    """Best-effort уведомить Kaspi о въезде (регистрация + бесплатное время).

    Не влияет на результат обработки события: любые ошибки только логируются,
    чтобы сбой Kaspi не ломал приём ANPR-событий.
    """
    if not settings.kaspi_autopay_enabled:
        return
    try:
        await KaspiAutoPayClient().enter(
            parking.plate_number,
            parking.id,
            free_time=settings.kaspi_free_time_seconds,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Kaspi autopay enter упал (не критично) для %s", parking.plate_number
        )


async def _autopay_exit(
    session: AsyncSession, parking: ParkingSession, due: float
) -> bool:
    """Попытка автосписания долга через Kaspi при выезде.

    Возвращает True, если списание прошло (сессию можно выпускать). При
    USER_NOT_FOUND — водитель не подключил автосписание, откатываемся на ручную
    оплату (False). Прочие ошибки (INSUFFICIENT_FUNDS и т.п.) фиксируем в Payment.
    """
    result = await KaspiAutoPayClient().exit(parking.plate_number, due, parking.id)
    if result.is_success:
        session.add(
            Payment(
                session_id=parking.id,
                amount=due,
                currency="KZT",
                status=PaymentStatus.PAID,
                provider="kaspi_autopay",
                provider_payment_id=result.request_id,
                provider_txn_id=result.transaction_id,
                paid_at=datetime.now(timezone.utc),
            )
        )
        parking.paid_amount = round((parking.paid_amount or 0.0) + due, 2)
        logger.info(
            "Kaspi autopay: сессия #%s (%s) списано %.2f (txn=%s)",
            parking.id,
            parking.plate_number,
            due,
            result.transaction_id,
        )
        return True

    if result.error_code and result.error_code != "USER_NOT_FOUND":
        # Фиксируем неуспешную попытку для разбора (карта отклонена, нет средств…)
        session.add(
            Payment(
                session_id=parking.id,
                amount=due,
                currency="KZT",
                status=PaymentStatus.FAILED,
                provider="kaspi_autopay",
                provider_payment_id=result.request_id,
                error_code=result.error_code,
            )
        )
    logger.info(
        "Kaspi autopay не прошёл для %s: %s",
        parking.plate_number,
        result.error_code or "USER_NOT_FOUND",
    )
    return False


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

    # ТС-7: направление не определено — сессии не трогаем, событие в ручную
    # проверку; оператор назначит ENTRY/EXIT через админку.
    event.flag = EventFlag.UNKNOWN_DIRECTION
    logger.info("direction=UNKNOWN для %s — на ручную проверку", event.plate_number)
    return SessionResult("ignored", detail="direction=UNKNOWN")


async def _open_session(
    session: AsyncSession,
    event: RecognitionEvent,
    gate_id: int | None = None,
    access: AccessEntry | None = None,
) -> ParkingSession:
    """Создать новую активную сессию по событию въезда.

    `access` — эффективная запись списка (зелёный/жёлтый) → метка сессии для
    расчёта оплаты при выезде.
    """
    access_type = None
    free_until = None
    if access is not None:
        if access.list_type == AccessListType.GREEN:
            access_type = AccessType.GREEN
        elif access.list_type == AccessListType.YELLOW:
            access_type = AccessType.YELLOW
            free_until = access.valid_until
    parking = ParkingSession(
        plate_number=event.plate_number,
        status=SessionStatus.ACTIVE,
        entry_time=event.event_time,
        last_seen=event.event_time,
        entry_event_id=event.id,
        entry_camera_id=event.camera_id,
        gate_id=gate_id,
        access_type=access_type,
        free_until=free_until,
    )
    session.add(parking)
    await session.flush()
    await _autopay_enter(session, parking)
    return parking


async def _handle_entry(
    session: AsyncSession, event: RecognitionEvent
) -> SessionResult:
    gate_id = await _resolve_gate_id(session, event)

    # Списки доступа (итерация 3): красный — не пускаем + сигнал; зелёный/жёлтый —
    # метим сессию для бесплатного/льготного проезда.
    access = await resolve_access(session, event.plate_number, gate_id)
    if access is not None and access.list_type == AccessListType.RED:
        event.flag = EventFlag.ACCESS_DENIED_RED
        await record_alert(
            session,
            AlertKind.RED_LIST,
            plate=event.plate_number,
            gate_id=gate_id,
            message=f"Красный список: {event.plate_number} на шлагбауме {gate_id}",
        )
        logger.warning(
            "ACCESS DENIED (красный список): %s на шлагбауме %s — шлагбаум закрыт, "
            "сигнал ответственному",
            event.plate_number,
            gate_id,
        )
        return SessionResult("access_denied_red", detail="красный список")

    active = await _find_active_at_gate(session, event.plate_number, gate_id)  # type: ignore[arg-type]
    if active is not None:
        window = timedelta(seconds=settings.entry_restart_window_seconds)
        reentry = timedelta(seconds=settings.reentry_new_session_seconds)
        ev_at = _as_aware(event.event_time)
        last = _as_aware(active.last_seen) or _as_aware(active.entry_time)
        entry = _as_aware(active.entry_time)

        # ТС-3: новый въезд спустя большой промежуток = выезд был пропущен.
        # Старую сессию закрываем как auto_closed (на ручную проверку),
        # для машины открываем новую активную.
        if ev_at is not None and last is not None and (ev_at - last) > reentry:
            active.status = SessionStatus.AUTO_CLOSED
            logger.warning(
                "ENTRY при зависшей сессии #%s (%s): старая → auto_closed, "
                "открываем новую (пропущенный выезд?)",
                active.id,
                event.plate_number,
            )
            parking = await _open_session(session, event, gate_id, access)
            return SessionResult(
                "reentry_new_session",
                parking.id,
                detail=f"old={active.id} auto_closed",
            )

        # ТС-2: дубль на въезде — новую сессию не создаём, событие помечаем.
        event.flag = EventFlag.DUPLICATE

        # Машина стоит перед шлагбаумом и камера видит её несколько раз подряд —
        # стартом сессии считаем ПОСЛЕДНЕЕ событие серии (решение клиента):
        # водитель не платит за ожидание снаружи. Помечаем entry_adjusted,
        # полная история событий остаётся в recognition_event.
        #
        # Сдвигаем только пока дубли идут «подряд» (entry_restart_window) и
        # только вперёд — повторное распознавание машины, давно стоящей на
        # территории, не должно обнулять счёт.
        if (
            ev_at is not None
            and last is not None
            and entry is not None
            and entry <= ev_at
            and (ev_at - last) <= window
        ):
            active.entry_time = event.event_time
            active.last_seen = event.event_time
            active.entry_event_id = event.id
            if event.camera_id is not None:
                active.entry_camera_id = event.camera_id
            active.entry_adjusted = True
            logger.info(
                "ENTRY дубль: %s → старт сессии сдвинут на последнее событие",
                event.plate_number,
            )
            return SessionResult("entry_restarted", active.id)

        active.last_seen = event.event_time
        logger.info(
            "ENTRY дубль (вне окна): %s → обновлён только last_seen",
            event.plate_number,
        )
        return SessionResult("updated_last_seen", active.id)

    # ТС-9: точного совпадения нет, но есть активная сессия с номером,
    # отличающимся на 1 символ — возможная ошибка распознавания (O↔0, I↔1).
    # Автоматически ничего не делаем: событие на ручную проверку.
    near = await _find_similar_active(session, event.plate_number, gate_id)  # type: ignore[arg-type]
    if near is not None:
        event.flag = EventFlag.POSSIBLE_MISREAD
        logger.warning(
            "possible_misread: ENTRY %s похож на активную сессию #%s (%s) — "
            "ручная проверка",
            event.plate_number,
            near.id,
            near.plate_number,
        )
        return SessionResult(
            "possible_misread", near.id, detail=f"похож на {near.plate_number}"
        )

    parking = await _open_session(session, event, gate_id, access)
    logger.info("ENTRY: открыта сессия #%s для %s", parking.id, event.plate_number)
    return SessionResult("created", parking.id)


async def _handle_exit(session: AsyncSession, event: RecognitionEvent) -> SessionResult:
    gate_id = await _resolve_gate_id(session, event)
    active = await _find_active_at_gate(session, event.plate_number, gate_id)  # type: ignore[arg-type]

    if active is None:
        # Возможно, это повторный EXIT по уже закрытой сессии — гасим в окне дедупа
        recent = await _recently_closed(
            session,
            event.plate_number,  # type: ignore[arg-type]
            event.event_time,
            gate_id,
        )
        if recent is not None:
            recent.last_seen = event.event_time
            event.flag = EventFlag.DUPLICATE  # ТС-2: дубль события
            logger.info("EXIT дубль: %s → игнор", event.plate_number)
            return SessionResult("duplicate_exit", recent.id)

        # ТС-9: активной сессии с таким номером нет, но есть с номером ±1 символ —
        # возможно, OCR ошибся в символе. Чужую сессию не закрываем, на проверку.
        near = await _find_similar_active(session, event.plate_number, gate_id)  # type: ignore[arg-type]
        if near is not None:
            event.flag = EventFlag.POSSIBLE_MISREAD
            logger.warning(
                "possible_misread: EXIT %s похож на активную сессию #%s (%s) — "
                "ручная проверка",
                event.plate_number,
                near.id,
                near.plate_number,
            )
            return SessionResult(
                "possible_misread", near.id, detail=f"похож на {near.plate_number}"
            )

        # Выезд без активной сессии (ТЗ §6.2)
        event.flag = EventFlag.EVENT_WITHOUT_SESSION
        logger.warning(
            "event_without_session: выезд %s без активной сессии — уведомить admin",
            event.plate_number,
        )
        return SessionResult("event_without_session")

    # Стоимость за фактическое время стоянки по активному тарифу (ТЗ §3.4)
    entry = _as_aware(active.entry_time)
    exit_at = _as_aware(event.event_time)
    duration = None
    if entry is not None and exit_at is not None:
        duration = int((exit_at - entry).total_seconds())
        active.duration_seconds = duration
    tariff = await get_active_tariff(session)

    # Списки доступа (итерация 3): зелёный — бесплатно; жёлтый — бесплатно до
    # free_until, далее тариф на «перебор»; остальные — как обычно.
    if active.access_type == AccessType.GREEN:
        price = 0.0
        active.price = 0.0
    elif active.access_type == AccessType.YELLOW:
        free_until = _as_aware(active.free_until)
        billable = 0
        if exit_at is not None and free_until is not None and exit_at > free_until:
            billable = int((exit_at - free_until).total_seconds())
        price = tariff_price(billable, tariff) if tariff is not None else 0.0
        if tariff is not None:
            active.price = price
    else:
        price = tariff_price(duration, tariff) if duration is not None else 0.0
        if tariff is not None and duration is not None:
            active.price = price
    due = round(price - active.paid_amount, 2)

    # Автосписание Kaspi: пробуем списать долг с привязанной карты ДО отказа.
    # Успех → списание учтено (due=0), сессию выпускаем; иначе — ручная оплата.
    if due > 0.009 and settings.kaspi_autopay_enabled:
        try:
            if await _autopay_exit(session, active, due):
                due = 0.0
        except Exception:  # noqa: BLE001
            logger.exception(
                "Kaspi autopay exit упал для %s — переходим к ручной оплате",
                event.plate_number,
            )

    if due > 0.009:
        # ШЛАГБАУМ ЗАКРЫТ: недоплата. Сессия остаётся активной — ждём (до)оплату.
        active.last_seen = event.event_time
        logger.info(
            "EXIT ЗАПРЕЩЁН #%s (%s): нужна доплата %.0f (цена %.0f, оплачено %.0f)",
            active.id,
            event.plate_number,
            due,
            price,
            active.paid_amount,
        )
        return SessionResult("exit_denied_unpaid", active.id, detail=f"due={due:.0f}")

    # Оплачено (или бесплатно) — выпускаем, шлагбаум открыт
    active.exit_time = event.event_time
    active.last_seen = event.event_time
    active.exit_event_id = event.id
    active.exit_camera_id = event.camera_id
    active.status = SessionStatus.PAID
    logger.info(
        "EXIT #%s (%s): выпущен (цена %.0f, оплачено %.0f)",
        active.id,
        event.plate_number,
        price,
        active.paid_amount,
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
        # ТС-8: активная дольше порога = «зависла» — выводим в админке,
        # автоматически НЕ закрываем (только вручную)
        out.is_stale = out.parked_seconds >= settings.session_stale_after_hours * 3600
    else:
        out.parked_seconds = row.duration_seconds
    return out


@router.get("/parking-sessions", response_model=PaginatedSessions)
async def list_sessions(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    plate: str | None = Query(
        None, description="Поиск по номеру (частичное совпадение)"
    ),
    status: str | None = Query(
        None, description="active / unpaid / paid / cancelled / whitelist"
    ),
    gate_id: int | None = Query(None, description="Фильтр по шлагбауму/зоне"),
    date_from: date | None = Query(None, description="Фильтр по дате въезда (с)"),
    date_to: date | None = Query(None, description="Фильтр по дате въезда (по)"),
    stale: bool = Query(
        False, description="ТС-8: только зависшие активные (старше порога)"
    ),
    sort: str = Query("entry_time", description="Поле сортировки"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedSessions:
    """Список парковочных сессий с фильтрами, сортировкой и пагинацией."""
    conditions: list[ColumnElement[bool]] = []
    if plate:
        # Ищем по канону: в БД хранится нормализованный номер, а оператор может
        # ввести с пробелами/кириллицей.
        conditions.append(
            ParkingSession.plate_number.ilike(f"%{normalize_plate(plate)}%")
        )
    if status:
        conditions.append(ParkingSession.status == status.lower())
    if gate_id is not None:
        conditions.append(ParkingSession.gate_id == gate_id)
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
    if stale:
        # ТС-8: активные дольше порога — «зависшие», на ручной разбор
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=settings.session_stale_after_hours
        )
        conditions.append(ParkingSession.status == SessionStatus.ACTIVE)
        conditions.append(ParkingSession.entry_time <= cutoff)

    base = select(ParkingSession)
    for cond in conditions:
        base = base.where(cond)

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    sort_field = _SORT_FIELDS.get(sort, ParkingSession.entry_time)
    order_by = sort_field.asc() if order == "asc" else sort_field.desc()

    rows = (
        (
            await session.execute(
                base.order_by(order_by).offset((page - 1) * limit).limit(limit)
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


@router.get("/parking-sessions/unpaid", response_model=list[ParkingSessionOut])
async def list_unpaid_sessions(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ParkingSessionOut]:
    """Сессии, выехавшие без оплаты (долги)."""
    rows = (
        (
            await session.execute(
                select(ParkingSession)
                .where(ParkingSession.status == SessionStatus.UNPAID)
                .order_by(ParkingSession.exit_time.desc())
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


@router.post("/parking-sessions/{session_id}/cancel", response_model=ParkingSessionOut)
async def cancel_session(
    session_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ParkingSessionOut:
    """Ручное закрытие сессии админом (ТС-8: зависшие закрываем только вручную)."""
    row = await session.get(ParkingSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if row.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400, detail="Отменить можно только активную сессию"
        )
    row.status = SessionStatus.CANCELLED
    await session.flush()
    # updated_at генерируется БД (onupdate) — подтягиваем в async-контексте,
    # иначе сериализация упрётся в лениво-экспайрнутый атрибут
    await session.refresh(row)
    logger.info("Сессия #%s (%s) отменена вручную", row.id, row.plate_number)
    return _to_out(row)
