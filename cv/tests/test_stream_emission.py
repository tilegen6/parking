"""Онлайн-эмиссия событий из потока: один проезд = ровно одно событие.

Проверяем StreamPipeline изолированно, подменяя распознавание фейком: сам
детект/OCR тут не важен — важна логика трек→голосование→эмиссия на закрытии
трека + кулдаун по номеру. Так же тестируются track/vote в остальных тестах.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from recognizer.config import RecognizerConfig
from recognizer.pipeline import FrameResult
from recognizer.sources import Frame
from recognizer.stream import StreamPipeline

# трек закрывается через max_age(=5) кадров без детекции -> 6 пустых закрывают
GAP = [None] * 6


class _FakePipeline:
    """Отдаёт заранее заданный FrameResult на кадр; _emit копит события."""

    def __init__(self) -> None:
        self.next: FrameResult | None = None
        self.emitted: list[dict] = []

    def process_frame(self, image):  # noqa: ANN001
        return self.next

    def _emit(self, res: FrameResult, frame, sinks) -> dict:  # noqa: ANN001
        rec = {
            "plate_number": res.plate,
            "confidence": res.confidence,
            "direction": "ENTRY",
        }
        self.emitted.append(rec)
        return rec


def _frame(i: int = 0) -> Frame:
    return Frame(
        np.zeros((100, 100, 3), dtype=np.uint8),
        i,
        datetime.now(timezone.utc),
        "test",
    )


def _pass(plate: str, n: int = 12, x0: int = 10, conf: float = 0.9):
    """Кадры одной «едущей» машины: бокс смещается на 1 px (треки сливаются)."""
    return [
        FrameResult(
            plate=plate,
            confidence=conf,
            box=(x0 + i, x0 + i, x0 + 30 + i, x0 + 30 + i),
            is_valid=True,
            alts=[],
        )
        for i in range(n)
    ]


def _feed(sp: StreamPipeline, pipe: _FakePipeline, seq: list) -> list[dict]:
    out: list[dict] = []
    for r in seq:
        pipe.next = r
        out += sp.process(_frame())
    return out


def _make(cfg: RecognizerConfig | None = None, clock=None):
    pipe = _FakePipeline()
    # Пороги качества обнулены: кадры здесь синтетические (однотонные), их отсеял
    # бы фильтр смаза/темноты, а эти тесты проверяют ЛОГИКУ ЭМИССИИ, а не качество
    # кадра. Сам фильтр проверяется отдельно — tests/test_stream_quality_gate.py.
    cfg = cfg or RecognizerConfig(
        min_hits=3, cooldown_seconds=60, blur_threshold=0.0, dark_threshold=0.0
    )
    sp = StreamPipeline(pipe, cfg, sinks={}, clock=clock or (lambda: 0.0))
    return sp, pipe


def test_single_pass_emits_exactly_one_event():
    sp, pipe = _make()
    emitted = _feed(sp, pipe, _pass("127AST02") + GAP)
    assert len(emitted) == 1
    assert emitted[0]["plate_number"] == "127AST02"
    assert len(pipe.emitted) == 1  # ровно один POST в бэкенд


def test_two_cars_emit_two_events():
    sp, pipe = _make()
    seq = _pass("127AST02", x0=10) + GAP + _pass("888XYZ05", x0=200) + GAP
    emitted = _feed(sp, pipe, seq)
    assert len(emitted) == 2
    assert {e["plate_number"] for e in emitted} == {"127AST02", "888XYZ05"}


def test_flicker_within_track_still_one_event():
    # номер пропал на 1 кадр (в пределах max_age) и вернулся -> тот же трек
    sp, pipe = _make()
    seq = _pass("127AST02", n=5) + [None] + _pass("127AST02", n=5, x0=15) + GAP
    emitted = _feed(sp, pipe, seq)
    assert len(emitted) == 1


def test_below_min_hits_not_emitted():
    # машина мелькнула всего 2 кадра -> ниже порога min_hits -> нет события
    sp, pipe = _make(
        RecognizerConfig(
            min_hits=3, cooldown_seconds=60, blur_threshold=0.0, dark_threshold=0.0
        )
    )
    emitted = _feed(sp, pipe, _pass("127AST02", n=2) + GAP)
    assert emitted == []


def test_same_plate_suppressed_within_cooldown_then_emitted_after():
    t = {"v": 0.0}
    sp, pipe = _make(
        RecognizerConfig(
            min_hits=3, cooldown_seconds=60, blur_threshold=0.0, dark_threshold=0.0
        ),
        clock=lambda: t["v"],
    )

    first = _feed(sp, pipe, _pass("127AST02") + GAP)  # emit @ t=0
    assert len(first) == 1

    t["v"] = 30.0  # в пределах кулдауна
    within = _feed(sp, pipe, _pass("127AST02") + GAP)
    assert within == []

    t["v"] = 90.0  # кулдаун прошёл (90-0 >= 60)
    after = _feed(sp, pipe, _pass("127AST02") + GAP)
    assert len(after) == 1


def test_flush_closes_open_track():
    # машина в кадре, потока нет GAP -> на stop() flush() эмитит открытый трек
    sp, pipe = _make()
    mid = _feed(sp, pipe, _pass("127AST02"))
    assert mid == []  # трек ещё открыт, событий нет
    assert len(sp.flush()) == 1
