"""Тесты Payment Service: создание платежа, webhook, идемпотентность."""

from datetime import datetime, timezone

from src.models import ParkingSession, SessionStatus
from src.modules.payment import (
    create_payment_for_session,
    mark_paid_by_provider_id,
)

T0 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


async def _unpaid_session(db, price: float = 500.0) -> ParkingSession:
    sess = ParkingSession(
        plate_number="123ABC02",
        status=SessionStatus.UNPAID,
        entry_time=T0,
        price=price,
    )
    db.add(sess)
    await db.flush()
    return sess


async def test_create_payment_is_pending(db):
    sess = await _unpaid_session(db, price=500)
    p = await create_payment_for_session(db, sess)
    assert p.status == "pending"
    assert p.amount == 500
    assert p.session_id == sess.id
    assert p.provider_payment_id  # провайдер выдал id
    assert p.pay_url  # ссылка/страница оплаты


async def test_webhook_marks_payment_and_session_paid(db):
    sess = await _unpaid_session(db, price=500)
    p = await create_payment_for_session(db, sess)
    result = await mark_paid_by_provider_id(db, p.provider_payment_id)
    assert result is not None
    assert result.status == "paid"
    assert result.paid_at is not None
    await db.refresh(sess)
    assert sess.status == SessionStatus.PAID


async def test_webhook_is_idempotent(db):
    sess = await _unpaid_session(db, price=500)
    p = await create_payment_for_session(db, sess)
    r1 = await mark_paid_by_provider_id(db, p.provider_payment_id)
    r2 = await mark_paid_by_provider_id(db, p.provider_payment_id)
    assert r1 is not None and r2 is not None
    assert r1.status == "paid" and r2.status == "paid"
    assert r1.id == r2.id  # тот же платёж — дубля оплаты нет


async def test_webhook_unknown_id_returns_none(db):
    assert await mark_paid_by_provider_id(db, "does-not-exist") is None
