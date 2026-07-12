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
