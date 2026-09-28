"""Тест CV-сервиса через FastAPI TestClient (движок template, без torch)."""

import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

import service  # noqa: E402
from recognizer import synth  # noqa: E402
from recognizer.config import RecognizerConfig  # noqa: E402


def _client() -> TestClient:
    cfg = RecognizerConfig(
        engine="template", detector="whole", confidence_threshold=0.5
    )
    return TestClient(service.create_app(cfg))


def test_health():
    r = _client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine"] == "template"


def test_recognize_synthetic_plate():
    img = synth.render_plate("123ABC02")
    _, buf = cv2.imencode(".png", img)
    r = _client().post(
        "/recognize",
        files={"file": ("plate.png", buf.tobytes(), "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["plate_number"] == "123ABC02"
    assert body["is_valid"] is True
    assert body["annotated_image"].startswith("data:image/png;base64,")
    assert isinstance(body["candidates"], list)


def test_recognize_rejects_non_image():
    r = _client().post(
        "/recognize",
        files={"file": ("x.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 400


def test_versions_exposes_detector_and_ocr_axes():
    """/versions отдаёт две независимые оси — детекторы и OCR-движки."""
    r = _client().get("/versions")
    assert r.status_code == 200
    body = r.json()
    det = {d["name"] for d in body["detectors"]}
    eng = {e["name"] for e in body["engines"]}
    assert {"plate", "yolo", "whole"} <= det
    assert {"fastplate", "easyocr", "template"} <= eng
    # у каждой оси есть человекочитаемая метка и признак доступности
    assert all("label" in d and "available" in d for d in body["detectors"])
    # встроенные (без пакета) всегда доступны
    whole = next(d for d in body["detectors"] if d["name"] == "whole")
    assert whole["available"] is True


def test_recognize_independent_engine_and_detector():
    """Можно задать детектор и OCR по отдельности, минуя пресеты."""
    img = synth.render_plate("123ABC02")
    _, buf = cv2.imencode(".png", img)
    r = _client().post(
        "/recognize",
        files={"file": ("plate.png", buf.tobytes(), "image/png")},
        data={"engine": "template", "detector": "whole"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "template"
    assert body["detector"] == "whole"
    assert body["plate_number"] == "123ABC02"


def test_recognize_rejects_unknown_engine():
    img = synth.render_plate("123ABC02")
    _, buf = cv2.imencode(".png", img)
    r = _client().post(
        "/recognize",
        files={"file": ("plate.png", buf.tobytes(), "image/png")},
        data={"engine": "nonexistent"},
    )
    assert r.status_code == 400
