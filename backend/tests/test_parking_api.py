"""Тесты HTTP API парковочных сессий: список, фильтры, сортировка, /active, /{id}."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio

from src.models import ParkingSession, SessionStatus

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def seeded(db):
    """Три сессии: A (закрыта, 111AAA01), B (active, 222BBB02), C (active, 111AAA01)."""
    a = ParkingSession(
        plate_number="111AAA01",
        status=SessionStatus.UNPAID,
        entry_time=NOW - timedelta(hours=2),
        exit_time=NOW - timedelta(hours=1),
        duration_seconds=3600,
    )
    b = ParkingSession(
        plate_number="222BBB02",
        status=SessionStatus.ACTIVE,
        entry_time=NOW - timedelta(minutes=30),
    )
    c = ParkingSession(
        plate_number="111AAA01",
        status=SessionStatus.ACTIVE,
        entry_time=NOW - timedelta(minutes=10),
    )
    db.add_all([a, b, c])
    await db.commit()
    return {"a": a.id, "b": b.id, "c": c.id}


async def test_list_all(client, seeded):
    r = await client.get("/api/v1/parking-sessions")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


async def test_filter_by_plate(client, seeded):
    r = await client.get("/api/v1/parking-sessions", params={"plate": "111"})
    assert r.status_code == 200
    assert r.json()["total"] == 2


async def test_filter_by_status(client, seeded):
    r = await client.get("/api/v1/parking-sessions", params={"status": "active"})
    assert r.json()["total"] == 2
    r2 = await client.get("/api/v1/parking-sessions", params={"status": "unpaid"})
    assert r2.json()["total"] == 1


async def test_filter_by_date(client, seeded):
    today = NOW.date().isoformat()
    r = await client.get("/api/v1/parking-sessions", params={"date_from": today})
    assert r.json()["total"] == 3
    yesterday = (NOW - timedelta(days=1)).date().isoformat()
    r2 = await client.get("/api/v1/parking-sessions", params={"date_to": yesterday})
    assert r2.json()["total"] == 0


async def test_sorting(client, seeded):
    asc = await client.get(
        "/api/v1/parking-sessions", params={"sort": "entry_time", "order": "asc"}
    )
    desc = await client.get(
        "/api/v1/parking-sessions", params={"sort": "entry_time", "order": "desc"}
    )
    first_asc = asc.json()["items"][0]["id"]
    first_desc = desc.json()["items"][0]["id"]
    assert first_asc == seeded["a"]  # самая старая запись
    assert first_desc == seeded["c"]  # самая свежая
    assert first_asc != first_desc


async def test_active_endpoint(client, seeded):
    r = await client.get("/api/v1/parking-sessions/active")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert all(s["status"] == "active" for s in items)
    # у активных есть посчитанное время стоянки
    assert all(s["parked_seconds"] is not None and s["parked_seconds"] >= 0 for s in items)


async def test_get_one_closed(client, seeded):
    r = await client.get(f"/api/v1/parking-sessions/{seeded['a']}")
    assert r.status_code == 200
    s = r.json()
    assert s["status"] == "unpaid"
    assert s["parked_seconds"] == 3600  # для закрытой = duration_seconds


async def test_get_missing_returns_404(client, seeded):
    r = await client.get("/api/v1/parking-sessions/999999")
    assert r.status_code == 404
