"""Тесты сборки события и соответствия контракту."""

import json
import os
from datetime import datetime, timezone

import pytest

from recognizer.events import Direction, build_event, normalize_direction

DT = datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc)


def test_build_event_contract_fields():
    ev = build_event(
        "123ABC01", "entry", confidence=0.9, camera_name="cam1", event_time=DT
    )
    c = ev.to_contract()
    assert c["plate_number"] == "123ABC01"
    assert c["direction"] == "ENTRY"
    assert c["source"] == "own-cv-v1"
    assert c["confidence"] == 0.9
    assert c["camera_name"] == "cam1"
    assert c["photos"] == {"plate": None, "vehicle": None}
    assert c["event_time"].startswith("2026-06-23T10:00:00")
    assert "+00:00" in c["event_time"]


def test_direction_normalization():
    assert normalize_direction("forward") == Direction.ENTRY
    assert normalize_direction("reverse") == Direction.EXIT
    assert normalize_direction("exit") == Direction.EXIT
    assert normalize_direction("entry") == Direction.ENTRY
    assert normalize_direction("???") == Direction.UNKNOWN
    assert normalize_direction(None) == Direction.UNKNOWN


def test_backend_json_shape():
    ev = build_event(
        "777AAA02", "exit", confidence=0.95, camera_name="c", event_time=DT
    )
    j = ev.to_backend_json()
    assert j == {
        "plateNumber": "777AAA02",
        "direction": "EXIT",
        "confidence": 0.95,
        "dateTime": ev.to_contract()["event_time"],
        "channelName": "c",
        "source": "own-cv-v1",
    }


def test_unrecognized_plate_is_null():
    ev = build_event("", "unknown", confidence=None, event_time=DT)
    c = ev.to_contract()
    assert c["plate_number"] is None
    assert c["confidence"] is None


def test_contract_matches_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "contract", "recognition-event.schema.json"
    )
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    ev = build_event(
        "123ABC01", "entry", confidence=0.9, camera_name="cam1", event_time=DT
    )
    jsonschema.validate(ev.to_contract(), schema)  # бросит при несоответствии
