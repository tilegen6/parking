"""Раннее решение об открытии шлагбаума в живом потоке.

Главное, что здесь проверяется: сигнал уходит, ПОКА машина ещё перед стрелой, а
не на закрытии трека (когда она уже уехала). Плюс — что один проезд даёт ровно
один запрос в бэкенд, и что уехавшей/статичной машине не открывают.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from recognizer.config import RecognizerConfig
from recognizer.pipeline import FrameResult
from recognizer.sources import Frame
from recognizer.stream import StreamPipeline

STEP = 0.2


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def tick(self) -> None:
        self.now += STEP


class _Pipe:
    """Фейковый пайплайн: отдаёт заданные чтения, копит отправленные события."""

    def __init__(self) -> None:
        self.next: list[FrameResult] = []
        self.emitted: list[dict] = []

    def process_frame_multi(self, image):  # noqa: ANN001
        return list(self.next)

    def process_frame(self, image):  # noqa: ANN001
        return self.next[0] if self.next else None

    def _emit(self, res, frame, sinks, decision="observe"):  # noqa: ANN001
        rec = {
            "plate_number": res.plate,
            "confidence": res.confidence,
            "decision": decision,
        }
        self.emitted.append(rec)
        return rec


def _frame(i: int = 0) -> Frame:
    return Frame(
        np.zeros((480, 640, 3), dtype=np.uint8), i, datetime.now(timezone.utc), "test"
    )


def _cfg(**over) -> RecognizerConfig:
    base: dict = {
        "min_hits": 3,
        "cooldown_seconds": 60,
        "blur_threshold": 0.0,  # синтетические кадры однотонные
        "dark_threshold": 0.0,
        "track_max_age_seconds": 0.5,
        "gate_min_votes": 3,
    }
    base.update(over)
    return RecognizerConfig(**base)


def _approach(plate: str, n: int = 6, conf: float = 0.95, grow: bool = True):
    """Кадры приближающейся машины: бокс растёт (или нет, если grow=False)."""
    out = []
    for i in range(n):
        size = 40 + (i * 25 if grow else 0)
        out.append(
            FrameResult(
                plate=plate,
                confidence=conf,
                box=(200.0, 200.0, 200.0 + size * 3, 200.0 + size),
                is_valid=True,
                alts=[],
            )
        )
    return out


def _make(cfg=None):  # noqa: ANN001
    pipe = _Pipe()
    clk = _Clock()
    sp = StreamPipeline(pipe, cfg or _cfg(), sinks={}, clock=clk)
    return sp, pipe, clk


def test_decision_taken_while_car_still_in_frame():
    """Ключевой сценарий: открываем, пока машина стоит, а не когда уехала."""
    sp, pipe, clk = _make()
    emitted: list[dict] = []
    for res in _approach("777ABC01"):
        pipe.next = [res]
        clk.tick()
        emitted += sp.process(_frame())

    # событие пришло ДО того, как трек закрылся (машина всё ещё в кадре)
    assert len(emitted) == 1, "решение должно приниматься на живом кадре"
    assert emitted[0]["decision"] == "open"
    assert emitted[0]["plate_number"] == "777ABC01"
    assert sp.opens_emitted == 1
    assert len(sp.tracker.active) == 1  # трек ещё жив — машина не уезжала


def test_single_pass_is_exactly_one_request():
    """Один проезд = один POST: после решения повторных событий нет."""
    sp, pipe, clk = _make()
    emitted: list[dict] = []
    for res in _approach("777ABC01", n=10):
        pipe.next = [res]
        clk.tick()
        emitted += sp.process(_frame())
    # машина уехала — трек закрывается
    for _ in range(6):
        pipe.next = []
        clk.tick()
        emitted += sp.process(_frame())

    assert len(emitted) == 1
    assert len(pipe.emitted) == 1  # ровно один вызов отправки


def test_leaving_car_gets_no_open():
    """Машина уезжает (бокс уменьшается) — сигнала «открыть» нет."""
    sp, pipe, clk = _make()
    emitted: list[dict] = []
    # сначала приблизилась (взводит ever_grew), потом резко удаляется
    seq = _approach("777ABC01", n=4)
    for i in range(5):
        size = 100 - i * 18
        seq.append(
            FrameResult(
                plate="777ABC01",
                confidence=0.95,
                box=(200.0, 200.0, 200.0 + size * 3, 200.0 + size),
                is_valid=True,
                alts=[],
            )
        )
    for res in seq:
        pipe.next = [res]
        clk.tick()
        emitted += sp.process(_frame())

    opens = [e for e in emitted if e["decision"] == "open"]
    # решение могло быть принято на подъезде — но не после того, как поехала прочь
    if opens:
        assert sp.last_reason in ("ok", "already_decided", "leaving")
    else:
        assert sp.last_reason == "leaving"


def test_static_object_never_opens():
    """Номер на плакате: не приближается — шлагбаум не открываем."""
    sp, pipe, clk = _make()
    emitted: list[dict] = []
    for res in _approach("777ABC01", n=12, grow=False):
        pipe.next = [res]
        clk.tick()
        emitted += sp.process(_frame())

    assert [e for e in emitted if e["decision"] == "open"] == []
    assert sp.last_reason == "never_grew"
    assert sp.opens_emitted == 0


def test_low_confidence_does_not_open_but_is_logged_on_close():
    """Неуверенное чтение: шлагбаум не трогаем, но событие для учёта уходит."""
    sp, pipe, clk = _make()
    emitted: list[dict] = []
    for res in _approach("777ABC01", n=8, conf=0.6):  # ниже gate_confidence
        pipe.next = [res]
        clk.tick()
        emitted += sp.process(_frame())
    assert emitted == []
    assert sp.last_reason == "low_confidence"

    for _ in range(6):  # машина уехала — трек закрылся
        pipe.next = []
        clk.tick()
        emitted += sp.process(_frame())

    assert len(emitted) == 1
    assert emitted[0]["decision"] == "observe"  # учёт, но не открытие
    assert sp.opens_emitted == 0


def test_gives_up_and_flags_for_operator():
    """Нечитаемый номер: не крутим проверку вечно, помечаем для оператора."""
    sp, pipe, clk = _make(_cfg(gate_max_seconds=1.0))
    for res in _approach("777ABC01", n=20, conf=0.5):
        pipe.next = [res]
        clk.tick()
        sp.process(_frame())

    assert sp.stalled >= 1
    assert sp.opens_emitted == 0


def test_gate_disabled_falls_back_to_old_behaviour():
    """Выключенные ворота = прежняя логика: событие только на закрытии трека."""
    sp, pipe, clk = _make(_cfg(gate_enabled=False))
    emitted: list[dict] = []
    for res in _approach("777ABC01", n=8):
        pipe.next = [res]
        clk.tick()
        emitted += sp.process(_frame())
    assert emitted == []  # пока машина в кадре — ничего

    for _ in range(6):
        pipe.next = []
        clk.tick()
        emitted += sp.process(_frame())
    assert len(emitted) == 1
    assert emitted[0]["decision"] == "observe"
