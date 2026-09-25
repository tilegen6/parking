"""Онлайн-эмиссия событий из потока: один проезд = ровно одно событие.

Проверяем StreamPipeline изолированно, подменяя распознавание фейком: сам
детект/OCR тут не важен — важна логика трек→голосование→эмиссия на закрытии
трека + кулдаун по номеру. Так же тестируются track/vote в остальных тестах.

Время здесь — часть логики: трек стареет по СЕКУНДАМ (шаг кадра в живом потоке
плавает от инференса и реконнектов), поэтому часы тикают на каждый кадр.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from recognizer.config import RecognizerConfig
from recognizer.pipeline import FrameResult
from recognizer.sources import Frame
from recognizer.stream import StreamPipeline

STEP = 0.2  # с/кадр (≈5 fps)
# Трек гаснет через track_max_age_seconds=0.5 → на 3-м пустом кадре; 6 с запасом.
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


class _Clock:
    """Монотонные часы, тикающие на каждый кадр (как в реальном потоке)."""

    def __init__(self, step: float = STEP) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        return self.now

    def tick(self) -> None:
        self.now += self.step


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


def _cfg(**over) -> RecognizerConfig:
    """Конфиг тестов эмиссии.

    Пороги качества обнулены: кадры синтетические (однотонные), фильтр смаза/тьмы
    отбраковал бы их, а здесь проверяется ЛОГИКА ЭМИССИИ (сам фильтр — в
    tests/test_stream_quality_gate.py).
    """
    base: dict = {
        "min_hits": 3,
        "cooldown_seconds": 60,
        "blur_threshold": 0.0,
        "dark_threshold": 0.0,
        "track_max_age_seconds": 0.5,
    }
    base.update(over)
    return RecognizerConfig(**base)


def _make(cfg: RecognizerConfig | None = None, clock=None):
    pipe = _FakePipeline()
    clk = clock or _Clock()
    sp = StreamPipeline(pipe, cfg or _cfg(), sinks={}, clock=clk)
    return sp, pipe, clk


def _feed(sp: StreamPipeline, pipe: _FakePipeline, seq: list, clock=None) -> list[dict]:
    out: list[dict] = []
    for r in seq:
        pipe.next = r
        if clock is not None:
            clock.tick()
        out += sp.process(_frame())
    return out


def test_single_pass_emits_exactly_one_event():
    sp, pipe, clk = _make()
    emitted = _feed(sp, pipe, _pass("127AST02") + GAP, clk)
    assert len(emitted) == 1
    assert emitted[0]["plate_number"] == "127AST02"
    assert len(pipe.emitted) == 1  # ровно один POST в бэкенд


def test_two_cars_emit_two_events():
    sp, pipe, clk = _make()
    seq = _pass("127AST02", x0=10) + GAP + _pass("888XYZ05", x0=200) + GAP
    emitted = _feed(sp, pipe, seq, clk)
    assert len(emitted) == 2
    assert {e["plate_number"] for e in emitted} == {"127AST02", "888XYZ05"}


def test_flicker_within_track_still_one_event():
    # номер пропал на 1 кадр (в пределах max_age) и вернулся -> тот же трек
    sp, pipe, clk = _make()
    seq = _pass("127AST02", n=5) + [None] + _pass("127AST02", n=5, x0=15) + GAP
    emitted = _feed(sp, pipe, seq, clk)
    assert len(emitted) == 1


def test_below_min_hits_not_emitted():
    # машина мелькнула всего 2 кадра -> ниже порога min_hits -> нет события
    sp, pipe, clk = _make()
    emitted = _feed(sp, pipe, _pass("127AST02", n=2) + GAP, clk)
    assert emitted == []


def test_same_plate_suppressed_within_cooldown_then_emitted_after():
    """Кулдаун по номеру гасит повтор; после его истечения событие снова идёт."""
    clk = _Clock()
    sp, pipe, _ = _make(clock=clk)

    first = _feed(sp, pipe, _pass("127AST02") + GAP, clk)
    assert len(first) == 1
    t_first = clk.now

    # второй проезд того же номера — внутри кулдауна (прошло ~3.6 с < 60 с)
    within = _feed(sp, pipe, _pass("127AST02") + GAP, clk)
    assert within == []
    assert clk.now - t_first < 60

    clk.now += 60  # кулдаун истёк
    after = _feed(sp, pipe, _pass("127AST02") + GAP, clk)
    assert len(after) == 1


def test_flush_closes_open_track():
    # машина в кадре, потока нет GAP -> на stop() flush() эмитит открытый трек
    sp, pipe, clk = _make()
    mid = _feed(sp, pipe, _pass("127AST02"), clk)
    assert mid == []  # трек ещё открыт, событий нет
    assert len(sp.flush()) == 1


def test_two_cars_in_same_frame_do_not_merge():
    """Две машины в одном кадре ведут РАЗНЫЕ треки (мультибокс).

    Раньше в трекер уходил один бокс на кадр: стоящая у стрелы машина и
    подъезжающая за ней делили общий трек, и их чтения смешивались в одном
    голосовании — отсюда «открыли не тому».
    """

    class _MultiPipeline(_FakePipeline):
        def process_frame_multi(self, image):  # noqa: ANN001
            return list(self.next or [])

    pipe = _MultiPipeline()
    clk = _Clock()
    sp = StreamPipeline(pipe, _cfg(), sinks={}, clock=clk)

    a = _pass("111AAA01", n=8, x0=10)
    b = _pass("222BBB02", n=8, x0=300)
    for i in range(8):
        pipe.next = [a[i], b[i]]
        clk.tick()
        sp.process(_frame())
    # обе машины уехали
    emitted: list[dict] = []
    for _ in GAP:
        pipe.next = []
        clk.tick()
        emitted += sp.process(_frame())

    assert {e["plate_number"] for e in emitted} == {"111AAA01", "222BBB02"}
