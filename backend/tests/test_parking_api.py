"""Тесты HTTP API парковочных сессий: список, фильтры, сортировка, /active, /{id}."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio

from src.models import (
    Direction,
    EventFlag,
    ParkingSession,
    RecognitionEvent,
    SessionStatus,
)

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
    assert all(
        s["parked_seconds"] is not None and s["parked_seconds"] >= 0 for s in items
    )


async def test_get_one_closed(client, seeded):
    r = await client.get(f"/api/v1/parking-sessions/{seeded['a']}")
    assert r.status_code == 200
    s = r.json()
    assert s["status"] == "unpaid"
    assert s["parked_seconds"] == 3600  # для закрытой = duration_seconds


async def test_get_missing_returns_404(client, seeded):
    r = await client.get("/api/v1/parking-sessions/999999")
    assert r.status_code == 404


# ── ТС-8: зависшие сессии (stale) + ручная отмена ──────────────────────────


async def test_stale_filter_and_manual_cancel(client, db):
    stale_s = ParkingSession(
        plate_number="333CCC03",
        status=SessionStatus.ACTIVE,
        entry_time=NOW - timedelta(hours=30),  # старше порога 24ч
    )
    fresh = ParkingSession(
        plate_number="444DDD04",
        status=SessionStatus.ACTIVE,
        entry_time=NOW - timedelta(minutes=10),
    )
    db.add_all([stale_s, fresh])
    await db.commit()

    r = await client.get("/api/v1/parking-sessions", params={"stale": "true"})
    assert r.status_code == 200
    data = r.json()
    plates = [i["plate_number"] for i in data["items"]]
    assert "333CCC03" in plates
    assert "444DDD04" not in plates
    stale_row = next(i for i in data["items"] if i["plate_number"] == "333CCC03")
    assert stale_row["is_stale"] is True

    # свежая активная в обычном списке is_stale=False
    r_all = await client.get("/api/v1/parking-sessions", params={"plate": "444"})
    assert r_all.json()["items"][0]["is_stale"] is False

    # ручная отмена (ТС-8: только вручную, автозакрытия нет)
    r2 = await client.post(f"/api/v1/parking-sessions/{stale_row['id']}/cancel")
    assert r2.status_code == 200
    assert r2.json()["status"] == "cancelled"

    # повторная отмена неактивной -> 400
    r3 = await client.post(f"/api/v1/parking-sessions/{stale_row['id']}/cancel")
    assert r3.status_code == 400


# ── ТС-7: оператор назначает направление событию UNKNOWN ───────────────────


async def test_assign_direction_to_unknown_event(client, db):
    ev = RecognitionEvent(
        plate_number="555EEE05",
        direction=Direction.UNKNOWN,
        event_time=NOW,
        confidence=0.95,
        flag=EventFlag.UNKNOWN_DIRECTION,
    )
    db.add(ev)
    await db.commit()

    r = await client.post(
        f"/api/v1/recognition/events/{ev.id}/direction",
        json={"direction": "ENTRY"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["direction"] == "ENTRY"
    assert body["session_action"] == "created"
    assert body["session_id"] is not None

    # направление уже определено -> 400
    r2 = await client.post(
        f"/api/v1/recognition/events/{ev.id}/direction",
        json={"direction": "EXIT"},
    )
    assert r2.status_code == 400


async def test_events_flag_filter(client, db):
    flagged = RecognitionEvent(
        plate_number="666FFF06",
        direction=Direction.EXIT,
        event_time=NOW,
        confidence=0.4,
        flag=EventFlag.LOW_CONFIDENCE,
    )
    clean = RecognitionEvent(
        plate_number="777GGG07",
        direction=Direction.ENTRY,
        event_time=NOW,
        confidence=0.95,
    )
    db.add_all([flagged, clean])
    await db.commit()

    r = await client.get("/api/v1/recognition/events", params={"flag": "any"})
    plates = [e["plate_number"] for e in r.json()["items"]]
    assert "666FFF06" in plates
    assert "777GGG07" not in plates

    r2 = await client.get(
        "/api/v1/recognition/events", params={"flag": "low_confidence"}
    )
    assert [e["plate_number"] for e in r2.json()["items"]] == ["666FFF06"]
