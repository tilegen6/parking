"""Остановка потока: реестр не копит мёртвые записи + открытый трек дослан.

Раньше /stream/stop оставлял хендл в _streams навсегда — /stream/status копил
десятки остановленных потоков до перезапуска сервиса; а открытый в момент
остановки трек терялся (событие не доезжало до бэкенда).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from service import StreamManager, _Handle


class _FakeSource:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FakeSP:
    """StreamPipeline-заглушка: на flush отдаёт одно «зависшее» событие."""

    def __init__(self, pending: list[dict] | None = None) -> None:
        self._pending = pending if pending is not None else [{"plate_number": "X1"}]
        # поля, которые читает StreamManager.status()
        self.frames_seen = 0
        self.events_emitted = 0
        self.last_plate = None

    def flush(self) -> list[dict]:
        out, self._pending = self._pending, []
        return out


def _manager_with(camera: str) -> tuple[StreamManager, _Handle]:
    mgr = StreamManager(pipeline_factory=lambda v: None, base_conf=0.5)
    handle = _Handle(camera, "demo", "entry", "template", _FakeSource(), _FakeSP())
    handle.thread = None  # тред уже отработал
    mgr._streams[camera] = handle
    return mgr, handle


def test_stop_removes_handle_from_registry():
    mgr, _ = _manager_with("cam-a")
    mgr.stop("cam-a")
    assert "cam-a" not in mgr._streams
    # повторный стоп — честный 404, а не «успех» по мёртвой записи
    with pytest.raises(HTTPException):
        mgr.stop("cam-a")


def test_stop_flushes_open_track():
    """Машина, которая была в кадре на момент стопа, всё равно даёт событие."""
    mgr, _ = _manager_with("cam-b")
    mgr.stop("cam-b")
    plates = [e["plate"] for e in mgr._events]
    assert "X1" in plates


def test_stop_all_clears_registry():
    mgr, _ = _manager_with("cam-c")
    mgr._streams["cam-d"] = _Handle(
        "cam-d", "demo", "entry", "template", _FakeSource(), _FakeSP([])
    )
    mgr._streams["cam-d"].thread = None
    mgr.stop_all()
    assert mgr._streams == {}
