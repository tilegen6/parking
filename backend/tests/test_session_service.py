"""Тесты Session Service — основные сценарии ТЗ (TC-1…TC-6 + аномалии)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.models import (
    Direction,
    EventFlag,
    ParkingSession,
    RecognitionEvent,
    SessionStatus,
    Tariff,
)
from src.modules import session as svc

T0 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


async def _emit(db, plate, direction, t, conf=0.95, cam=None):
    event = RecognitionEvent(
        plate_number=plate,
        direction=direction,
        event_time=t,
        confidence=conf,
        camera_id=cam,
    )
    db.add(event)
    await db.flush()
    result = await svc.handle_recognition_event(db, event)
    return event, result


async def test_entry_creates_active_session(db):
    _, r = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    assert r.action == "created"
    sess = await db.get(ParkingSession, r.session_id)
    assert sess.status == SessionStatus.ACTIVE
    assert sess.exit_time is None


async def test_duplicate_entry_updates_last_seen(db):
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    _, r2 = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(seconds=5))
    assert r2.action == "updated_last_seen"
    assert r2.session_id == r1.session_id
    total = (
        await db.execute(select(func.count()).select_from(ParkingSession))
    ).scalar_one()
    assert total == 1


async def test_entry_exit_closes_with_duration(db):
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    _, r3 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30))
    assert r3.action == "closed"
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.status == SessionStatus.UNPAID
    assert sess.duration_seconds == 1800


async def test_duplicate_exit_ignored(db):
    await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30))
    _, r = await _emit(
        db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30, seconds=3)
    )
    assert r.action == "duplicate_exit"


async def test_exit_without_session_flags_event(db):
    event, r = await _emit(db, "999ZZZ09", Direction.EXIT, T0)
    assert r.action == "event_without_session"
    assert event.flag == EventFlag.EVENT_WITHOUT_SESSION
    total = (
        await db.execute(select(func.count()).select_from(ParkingSession))
    ).scalar_one()
    assert total == 0


async def test_low_confidence_skips_session(db):
    event, r = await _emit(db, "777BBB07", Direction.ENTRY, T0, conf=0.5)
    assert r.action == "low_confidence"
    assert event.flag == EventFlag.LOW_CONFIDENCE


async def test_null_plate_is_low_confidence(db):
    _, r = await _emit(db, None, Direction.ENTRY, T0, conf=0.99)
    assert r.action == "low_confidence"


async def test_reentry_after_exit_creates_new_session(db):
    # выезд закрыл сессию -> следующий въезд = новая активная
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30))
    _, r2 = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(hours=2))
    assert r2.action == "created"
    assert r2.session_id != r1.session_id


async def test_exit_sets_price_from_active_tariff(db):
    # активный тариф: 0 беспл, 100/час, без потолка
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=100, daily_cap=None, is_active=True
        )
    )
    await db.flush()
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.price == 200  # 2 часа × 100


async def test_exit_without_tariff_leaves_price_none(db):
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.price is None
