"""Тесты шлагбаума: оплата до выезда + доплата за «добежавшее» время."""

from datetime import datetime, timedelta, timezone

from src.models import (
    Direction,
    ParkingSession,
    RecognitionEvent,
    SessionStatus,
    Tariff,
)
from src.modules import payment as pay_svc
from src.modules import session as sess_svc

T0 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


async def _tariff(db):
    # 100/час, без бесплатного периода, без потолка
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=100, daily_cap=None, is_active=True
        )
    )
    await db.flush()


async def _emit(db, plate, direction, t):
    ev = RecognitionEvent(
        plate_number=plate, direction=direction, event_time=t, confidence=0.95
    )
    db.add(ev)
    await db.flush()
    return await sess_svc.handle_recognition_event(db, ev)


async def test_exit_allowed_when_prepaid(db):
    await _tariff(db)
    r = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    sess = await db.get(ParkingSession, r.session_id)
    sess.paid_amount = 200  # оплатил ровно за 2 часа
    await db.flush()
    r2 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    assert r2.action == "closed"
    assert sess.status == SessionStatus.PAID
    assert sess.exit_time is not None


async def test_surcharge_when_time_exceeds_paid(db):
    # оплатил 2 часа (200), но выезжаю в 2ч03 -> цена 3 часа (300) -> доплата 100
    await _tariff(db)
    r = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    sess = await db.get(ParkingSession, r.session_id)
    sess.paid_amount = 200
    await db.flush()

    r2 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2, minutes=3))
    assert r2.action == "exit_denied_unpaid"
    assert r2.detail == "due=100"
    assert sess.status == SessionStatus.ACTIVE
    assert sess.exit_time is None

    # доплатил 100 (итого 300) -> выезжаю снова -> выпущен
    sess.paid_amount = 300
    await db.flush()
    r3 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2, minutes=3))
    assert r3.action == "closed"
    assert sess.status == SessionStatus.PAID


async def test_payment_covers_current_due_and_frees_exited(db):
    # выехавшая без оплаты (exit_time зафиксирован) -> платёж = долг, потом paid
    await _tariff(db)
    sess = ParkingSession(
        plate_number="123ABC02",
        status=SessionStatus.UNPAID,
        entry_time=T0,
        exit_time=T0 + timedelta(hours=2),
        paid_amount=0,
    )
    db.add(sess)
    await db.flush()

    p = await pay_svc.create_payment_for_session(db, sess)
    assert p.amount == 200  # долг за 2 часа
    await pay_svc.mark_paid_by_provider_id(db, p.provider_payment_id)
    assert sess.paid_amount == 200
    assert sess.status == SessionStatus.PAID
