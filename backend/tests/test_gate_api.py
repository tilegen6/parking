"""Тесты API шлагбаумов (итерация 1): CRUD + привязка камеры + фильтр сессий."""

from datetime import datetime, timedelta, timezone

from src.models import Camera, ParkingSession, SessionStatus

NOW = datetime.now(timezone.utc)


async def test_gate_crud(client):
    # создать
    r = await client.post(
        "/api/v1/gates",
        json={"name": "КПП двор", "zone": "Двор", "level": 1},
    )
    assert r.status_code == 201
    gate = r.json()
    gid = gate["id"]
    assert gate["name"] == "КПП двор"
    assert gate["level"] == 1
    assert gate["is_active"] is True

    # список
    r = await client.get("/api/v1/gates")
    assert r.status_code == 200
    assert any(g["id"] == gid for g in r.json())

    # обновить (частично)
    r = await client.put(f"/api/v1/gates/{gid}", json={"zone": "Внутренний двор"})
    assert r.status_code == 200
    assert r.json()["zone"] == "Внутренний двор"
    assert r.json()["name"] == "КПП двор"  # не затёрли

    # получить один
    r = await client.get(f"/api/v1/gates/{gid}")
    assert r.status_code == 200

    # удалить
    r = await client.delete(f"/api/v1/gates/{gid}")
    assert r.status_code == 204
    r = await client.get(f"/api/v1/gates/{gid}")
    assert r.status_code == 404


async def test_get_missing_gate_404(client):
    r = await client.get("/api/v1/gates/999999")
    assert r.status_code == 404


async def test_assign_camera_to_gate(client, db):
    g = await client.post("/api/v1/gates", json={"name": "Отель", "level": 2})
    gid = g.json()["id"]
    cam = Camera(name="cam-hotel")
    db.add(cam)
    await db.commit()

    r = await client.put(f"/api/v1/cameras/{cam.id}", json={"gate_id": gid})
    assert r.status_code == 200
    assert r.json()["gate_id"] == gid


async def test_sessions_filter_by_gate(client, db, operator_headers):
    g1 = await client.post("/api/v1/gates", json={"name": "Двор"})
    g2 = await client.post("/api/v1/gates", json={"name": "Отель", "level": 2})
    id1, id2 = g1.json()["id"], g2.json()["id"]

    db.add_all(
        [
            ParkingSession(
                plate_number="111AAA01",
                status=SessionStatus.ACTIVE,
                entry_time=NOW - timedelta(minutes=10),
                gate_id=id1,
            ),
            ParkingSession(
                plate_number="222BBB02",
                status=SessionStatus.ACTIVE,
                entry_time=NOW - timedelta(minutes=5),
                gate_id=id2,
            ),
        ]
    )
    await db.commit()

    r = await client.get(
        "/api/v1/parking-sessions", params={"gate_id": id1}, headers=operator_headers
    )
    plates = [i["plate_number"] for i in r.json()["items"]]
    assert plates == ["111AAA01"]
    # gate_id прокидывается в ответе
    assert r.json()["items"][0]["gate_id"] == id1
