"""Тесты агрегаций дашборда денег: доход за сегодня, неоплаченные, среднее время."""

from datetime import datetime, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.database import get_session
from src.models import ParkingSession, Payment, PaymentStatus, SessionStatus
from src.modules import payment as payment_module

T0 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def client(sessionmaker_):
    app = FastAPI()
    app.include_router(payment_module.router)

    async def _override_get_session():
        async with sessionmaker_() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_billing_stats(client, db):
    now = datetime.now(timezone.utc)
    s1 = ParkingSession(
        plate_number="A123BC01",
        status=SessionStatus.UNPAID,
        entry_time=T0,
        duration_seconds=3600,
        price=200,
    )
    s2 = ParkingSession(
        plate_number="B234CD02",
        status=SessionStatus.PAID,
        entry_time=T0,
        duration_seconds=7200,
        price=400,
    )
    db.add_all([s1, s2])
    await db.flush()
    db.add(
        Payment(
            session_id=s2.id,
            amount=400,
            currency="KZT",
            status=PaymentStatus.PAID,
            provider="mock",
            provider_payment_id="p1",
            paid_at=now,
        )
    )
    await db.commit()

    r = await client.get("/api/v1/dashboard/billing")
    assert r.status_code == 200
    body = r.json()
    assert body["revenue_today"] == 400
    assert body["unpaid_count"] == 1
    assert body["avg_parked_seconds"] == 5400  # (3600 + 7200) / 2


async def test_billing_stats_empty(client):
    r = await client.get("/api/v1/dashboard/billing")
    assert r.status_code == 200
    body = r.json()
    assert body["revenue_today"] == 0
    assert body["unpaid_count"] == 0
    assert body["avg_parked_seconds"] is None
