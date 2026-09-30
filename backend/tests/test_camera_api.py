"""Камеры: карточка с доступом к потоку, сборка RTSP-URL, проверка связи."""

from src.models import Camera, CameraStatus
from src.modules.camera import build_stream_url


def _payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Entry-Cam-1",
        "ip_address": "192.168.8.30",
        "type": "Hikvision",
        "location": "Въезд",
        "direction": "entry",
        "username": "admin",
        "password": "p@ss/word",
        "rtsp_port": 554,
    }
    base.update(over)
    return base


async def test_create_camera_hides_password_but_keeps_it(client, db):
    r = await client.post("/api/v1/cameras", json=_payload())
    assert r.status_code == 201, r.text
    body = r.json()

    # Пароль наружу не отдаём — только признак и замаскированный URL
    assert "password" not in body
    assert body["has_password"] is True
    assert body["username"] == "admin"
    assert body["stream_url_display"] == (
        "rtsp://admin:•••@192.168.8.30:554/Streaming/Channels/102"
    )

    stored = await db.get(Camera, body["id"])
    assert stored is not None and stored.password == "p@ss/word"


def test_build_stream_url_escapes_password():
    """Пароль с @ и / обязан быть url-кодирован, иначе ffmpeg разберёт URL криво."""
    camera = Camera(
        name="c",
        ip_address="10.0.0.5",
        username="admin",
        password="p@ss/word",
        rtsp_port=8554,
        stream_path="Streaming/Channels/101",
    )
    assert build_stream_url(camera) == (
        "rtsp://admin:p%40ss%2Fword@10.0.0.5:8554/Streaming/Channels/101"
    )


def test_build_stream_url_manual_wins():
    """Ручной URL (телефон/NVR) побеждает сборку по частям."""
    camera = Camera(
        name="phone",
        ip_address="10.0.0.5",
        rtsp_port=554,
        stream_url="http://100.64.0.2:4747/video",
    )
    assert build_stream_url(camera) == "http://100.64.0.2:4747/video"


def test_build_stream_url_without_target():
    assert build_stream_url(Camera(name="empty", rtsp_port=554)) is None


async def test_update_keeps_password_when_field_empty(client, db):
    created = (await client.post("/api/v1/cameras", json=_payload())).json()

    r = await client.put(
        f"/api/v1/cameras/{created['id']}",
        json={"location": "Выезд", "password": ""},
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_password"] is True

    stored = await db.get(Camera, created["id"])
    await db.refresh(stored)
    assert stored.password == "p@ss/word"
    assert stored.location == "Выезд"


async def test_check_requires_address(client):
    created = (await client.post("/api/v1/cameras", json={"name": "no-address"})).json()
    r = await client.post(f"/api/v1/cameras/{created['id']}/check")
    assert r.status_code == 400


async def test_check_marks_offline_when_unreachable(client, db):
    """Недостижимый адрес → offline (а не «unknown навсегда»)."""
    created = (
        await client.post(
            "/api/v1/cameras",
            # 192.0.2.0/24 — TEST-NET-1, гарантированно никуда не ведёт
            json=_payload(name="dead-cam", ip_address="192.0.2.1", rtsp_port=554),
        )
    ).json()

    r = await client.post(f"/api/v1/cameras/{created['id']}/check")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reachable"] is False
    assert body["status"] == CameraStatus.OFFLINE

    stored = await db.get(Camera, created["id"])
    await db.refresh(stored)
    assert stored.status == CameraStatus.OFFLINE


async def test_stream_start_requires_direction(client):
    created = (
        await client.post("/api/v1/cameras", json=_payload(direction=None))
    ).json()
    r = await client.post(f"/api/v1/cameras/{created['id']}/stream/start")
    assert r.status_code == 400
    assert "направление" in r.json()["detail"]


async def test_delete_camera(client):
    created = (await client.post("/api/v1/cameras", json=_payload())).json()
    assert (await client.delete(f"/api/v1/cameras/{created['id']}")).status_code == 204
    assert (await client.get(f"/api/v1/cameras/{created['id']}")).status_code == 404


async def test_event_marks_camera_online(client, db):
    """Событие от камеры = она жива: статус online и время последнего сигнала."""
    created = (await client.post("/api/v1/cameras", json=_payload())).json()
    assert created["status"] == "unknown"

    r = await client.post(
        "/api/v1/hikvision/anpr-event",
        json={
            "plateNumber": "777ABC01",
            "direction": "ENTRY",
            "confidence": 0.97,
            "deviceName": "Entry-Cam-1",
        },
    )
    assert r.status_code == 201, r.text

    stored = await db.get(Camera, created["id"])
    await db.refresh(stored)
    assert stored.status == CameraStatus.ONLINE
    assert stored.last_seen_at is not None
