"""Invalid device input must not write events, sessions or images."""

from unittest.mock import Mock

import pytest
from sqlalchemy import func, select

from src.models import ParkingSession, RecognitionEvent
from src.storage import storage


@pytest.mark.parametrize(
    "body,content_type",
    [
        ('{"broken":', "application/json"),
        ("[]", "application/json"),
        ("{}", "application/json"),
        ('{"plateNumber":123}', "application/json"),
        ('{"plateNumber":"123ABC02","confidence":"NaN"}', "application/json"),
        ('{"plateNumber":"123ABC02","dateTime":"bad-time"}', "application/json"),
        ("<EventNotificationAlert>", "application/xml"),
        ("<unrelated/>", "application/xml"),
    ],
)
async def test_invalid_ingest_is_rejected_before_writes(
    client, db, monkeypatch, body, content_type
):
    upload = Mock()
    monkeypatch.setattr(storage, "upload", upload)
    response = await client.post(
        "/api/v1/hikvision/anpr-event",
        content=body,
        headers={"Content-Type": content_type},
    )
    assert response.status_code == 400
    assert (await db.scalar(select(func.count()).select_from(RecognitionEvent))) == 0
    assert (await db.scalar(select(func.count()).select_from(ParkingSession))) == 0
    upload.assert_not_called()


@pytest.mark.parametrize("event", [None, ("event.xml", b"<broken", "application/xml")])
async def test_invalid_multipart_does_not_upload_images(client, db, monkeypatch, event):
    upload = Mock()
    monkeypatch.setattr(storage, "upload", upload)
    files = {"photo": ("plate.jpg", b"synthetic-photo", "image/jpeg")}
    if event:
        files["event"] = event
    response = await client.post("/api/v1/hikvision/anpr-event", files=files)
    assert response.status_code == 400
    assert await db.scalar(select(func.count()).select_from(RecognitionEvent)) == 0
    upload.assert_not_called()


@pytest.mark.parametrize("kind", ["json", "xml", "multipart-json", "multipart-xml"])
async def test_valid_ingest_formats(client, db, kind):
    json_body = '{"plateNumber":"123ABC02","direction":"ENTRY","confidence":0.95}'
    xml_body = (
        "<EventNotificationAlert><licensePlate>123ABC02</licensePlate>"
        "<direction>forward</direction><confidenceLevel>95</confidenceLevel>"
        "</EventNotificationAlert>"
    )
    if kind.startswith("multipart"):
        response = await client.post(
            "/api/v1/hikvision/anpr-event",
            files={
                "event": (
                    "event." + kind.split("-")[1],
                    json_body if kind.endswith("json") else xml_body,
                    "application/" + kind.split("-")[1],
                )
            },
        )
    else:
        response = await client.post(
            "/api/v1/hikvision/anpr-event",
            content=json_body if kind == "json" else xml_body,
            headers={"Content-Type": "application/" + kind},
        )
    assert response.status_code == 201, response.text
    assert response.json()["session_action"] == "created"
    assert await db.scalar(select(func.count()).select_from(RecognitionEvent)) == 1


@pytest.mark.parametrize("norm_status", ["unknown_format", "ambiguous"])
async def test_untrusted_cv_format_cannot_create_session(client, db, norm_status):
    response = await client.post(
        "/api/v1/hikvision/anpr-event",
        json={
            "plateNumber": "ABQ0301",
            "plateRaw": "ABQ0301",
            "direction": "ENTRY",
            "confidence": 0.99,
            "normalizationStatus": norm_status,
            "source": "own-cv-v1",
        },
    )
    assert response.status_code == 201
    assert response.json()["session_action"] == "low_confidence"
    assert await db.scalar(select(func.count()).select_from(ParkingSession)) == 0
    event = (await db.execute(select(RecognitionEvent))).scalar_one()
    assert event.plate_raw == "ABQ0301"
    assert event.confidence == 0.99


async def test_corrected_cv_plate_keeps_raw_and_creates_session(client, db):
    response = await client.post(
        "/api/v1/hikvision/anpr-event",
        json={
            "plateNumber": "237BLM01",
            "plateRaw": "237BLMO1",
            "direction": "ENTRY",
            "confidence": 0.95,
            "normalizationStatus": "corrected",
            "source": "own-cv-v1",
        },
    )
    assert response.status_code == 201
    assert response.json()["session_action"] == "created"
    event = (await db.execute(select(RecognitionEvent))).scalar_one()
    assert event.plate_number == "237BLM01"
    assert event.plate_raw == "237BLMO1"
    assert '"normalizationStatus": "corrected"' in event.raw_payload
