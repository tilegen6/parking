"""Тесты Payment API: создание платежа, статус, webhook, 404."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.database import get_session
from src.models import ParkingSession, SessionStatus, Tariff
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


async def _seed_session(db) -> ParkingSession:
    # тариф 100/час + выехавшая без оплаты сессия на 2 часа -> долг 200
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=100, daily_cap=None, is_active=True
        )
    )
    sess = ParkingSession(
        plate_number="123ABC02",
        status=SessionStatus.UNPAID,
        entry_time=T0,
        exit_time=T0 + timedelta(hours=2),
        paid_amount=0,
    )
    db.add(sess)
    await db.commit()
    return sess


async def test_create_payment_endpoint(client, db):
    sess = await _seed_session(db)
    r = await client.post("/api/v1/payments/create", json={"session_id": sess.id})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["amount"] == 200  # долг за 2 часа
    assert body["pay_url"]
    assert body["session_id"] == sess.id


async def test_webhook_pays_session(client, db):
    sess = await _seed_session(db)
    created = (
        await client.post("/api/v1/payments/create", json={"session_id": sess.id})
    ).json()
    r = await client.post(
        "/api/v1/payments/webhook",
        json={"provider_payment_id": created["provider_payment_id"]},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paid"
    await db.refresh(sess)
    assert sess.status == SessionStatus.PAID


async def test_status_endpoint(client, db):
    sess = await _seed_session(db)
    created = (
        await client.post("/api/v1/payments/create", json={"session_id": sess.id})
    ).json()
    r = await client.get(f"/api/v1/payments/status/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


async def test_create_missing_session_returns_404(client):
    r = await client.post("/api/v1/payments/create", json={"session_id": 9999})
    assert r.status_code == 404
