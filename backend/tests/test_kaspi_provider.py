"""Тесты онлайн-протокола Kaspi (входящий check/pay): коды, идемпотентность, IP."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.config import settings
from src.core.security import verify_kaspi_source
from src.database import get_session
from src.models import ParkingSession, Payment, SessionStatus, Tariff
from src.modules import kaspi as kaspi_module

PLATE = "123ABC02"


def _mount(sessionmaker_, *, secured: bool = False) -> FastAPI:
    """Приложение с роутером Kaspi. secured=True — оставить IP-проверку включённой."""
    app = FastAPI()
    app.include_router(kaspi_module.router)

    async def _override_get_session():
        async with sessionmaker_() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = _override_get_session
    if not secured:
        app.dependency_overrides[verify_kaspi_source] = lambda: None
    return app


@pytest_asyncio.fixture
async def client(sessionmaker_):
    transport = ASGITransport(app=_mount(sessionmaker_))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_owing_session(db, *, minutes_ago: int = 90) -> ParkingSession:
    """Активная сессия с долгом 200 (тариф 100/час, стоит ~1.5 ч → 2 биллинг-часа)."""
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=100, daily_cap=None, is_active=True
        )
    )
    sess = ParkingSession(
        plate_number=PLATE,
        status=SessionStatus.ACTIVE,
        entry_time=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        paid_amount=0,
    )
    db.add(sess)
    await db.commit()
    return sess


async def test_check_returns_due_for_owing_plate(client, db, monkeypatch):
    monkeypatch.setattr(settings, "kaspi_provider_response_format", "json")
    await _seed_owing_session(db)
    r = await client.get(
        "/api/kaspi/pay",
        params={"command": "check", "txn_id": "1", "account": PLATE, "sum": "0"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == 0
    assert body["sum"] == "200.00"


async def test_check_unknown_plate_returns_not_found(client, db, monkeypatch):
    monkeypatch.setattr(settings, "kaspi_provider_response_format", "json")
    r = await client.get(
        "/api/kaspi/pay",
        params={"command": "check", "txn_id": "1", "account": "999ZZZ09", "sum": "0"},
    )
    assert r.json()["result"] == 1


async def test_pay_credits_session_and_returns_prv_txn(client, db, monkeypatch):
    monkeypatch.setattr(settings, "kaspi_provider_response_format", "json")
    sess = await _seed_owing_session(db)
    r = await client.get(
        "/api/kaspi/pay",
        params={
            "command": "pay",
            "txn_id": "555",
            "account": PLATE,
            "sum": "200.00",
            "txn_date": "20260710120000",
        },
    )
    body = r.json()
    assert body["result"] == 0
    assert body["prv_txn_id"]
    await db.refresh(sess)
    assert sess.paid_amount == 200


async def test_pay_is_idempotent_by_txn_id(client, db, monkeypatch):
    monkeypatch.setattr(settings, "kaspi_provider_response_format", "json")
    sess = await _seed_owing_session(db)
    params = {
        "command": "pay",
        "txn_id": "777",
        "account": PLATE,
        "sum": "200.00",
        "txn_date": "20260710120000",
    }
    first = (await client.get("/api/kaspi/pay", params=params)).json()
    second = (await client.get("/api/kaspi/pay", params=params)).json()
    assert first["result"] == 0
    assert second["result"] == 3  # уже оплачено — без двойного списания
    # Только один платёж и одно списание в сессию
    payments = (
        await db.execute(select(func.count()).select_from(Payment))
    ).scalar_one()
    assert payments == 1
    await db.refresh(sess)
    assert sess.paid_amount == 200


async def test_pay_xml_response_shape(client, db, monkeypatch):
    monkeypatch.setattr(settings, "kaspi_provider_response_format", "xml")
    await _seed_owing_session(db)
    r = await client.get(
        "/api/kaspi/pay",
        params={
            "command": "pay",
            "txn_id": "900",
            "account": PLATE,
            "sum": "200.00",
        },
    )
    assert r.headers["content-type"].startswith("application/xml")
    assert "<result>0</result>" in r.text
    assert "<prv_txn>" in r.text


async def test_disallowed_ip_is_rejected(sessionmaker_, monkeypatch):
    monkeypatch.setattr(
        settings, "kaspi_allowed_ips", "194.187.247.152,194.187.245.108"
    )
    transport = ASGITransport(app=_mount(sessionmaker_, secured=True))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/api/kaspi/pay",
            params={"command": "check", "txn_id": "1", "account": PLATE, "sum": "0"},
            headers={"X-Forwarded-For": "9.9.9.9"},
        )
    assert r.status_code == 403
