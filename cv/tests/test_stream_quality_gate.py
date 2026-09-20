"""CV-2: фильтр качества кадра в ЖИВОМ потоке.

Раньше `frame_ok` вызывался только в офлайн-обработке файла (`run_video`), а боевой
RTSP шёл мимо — смазанные и тёмные кадры попадали в OCR и портили голосование.

Ключевая тонкость фикса: отбракованный кадр не должен «замораживать» треки. Если
просто пропустить кадр целиком, машина, уехавшая на серии плохих кадров, никогда не
закроет трек — и событие о проезде потеряется совсем. Поэтому плохой кадр трактуется
как кадр БЕЗ детекций: OCR не зовём, но трекер старим.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from recognizer.config import RecognizerConfig
from recognizer.pipeline import FrameResult
from recognizer.sources import Frame
from recognizer.stream import StreamPipeline

GAP_LEN = 6  # max_age(5) + 1 — столько «пустых» кадров закрывают трек


class _FakePipeline:
    def __init__(self) -> None:
        self.next: FrameResult | None = None
        self.emitted: list[dict] = []
        self.process_calls = 0

    def process_frame(self, image):  # noqa: ANN001
        self.process_calls += 1
        return self.next

    def _emit(self, res: FrameResult, frame, sinks) -> dict:  # noqa: ANN001
        rec = {"plate_number": res.plate, "confidence": res.confidence}
        self.emitted.append(rec)
        return rec


def _good_image() -> np.ndarray:
    """Кадр, проходящий фильтр: яркий и с достаточной детализацией (шум)."""
    rng = np.random.default_rng(42)
    return rng.integers(80, 255, size=(100, 100, 3), dtype=np.uint8)


def _dark_image() -> np.ndarray:
    """Тёмный кадр — ночь без подсветки."""
    return np.zeros((100, 100, 3), dtype=np.uint8)


def _frame(image: np.ndarray, i: int = 0) -> Frame:
    return Frame(image, i, datetime.now(timezone.utc), "test")


def _det(plate: str, i: int) -> FrameResult:
    return FrameResult(
        plate=plate,
        confidence=0.9,
        box=(10 + i, 10 + i, 40 + i, 40 + i),
        is_valid=True,
        alts=[],
    )


def _make():
    pipe = _FakePipeline()
    # Пороги «боевые»: dark_threshold=40 отсеет чёрный кадр, blur — однотонный.
    cfg = RecognizerConfig(
        min_hits=3, cooldown_seconds=60, blur_threshold=100.0, dark_threshold=40.0
    )
    sp = StreamPipeline(pipe, cfg, sinks={}, clock=lambda: 0.0)
    return sp, pipe


def test_dark_frame_skips_ocr_and_counts_dropped():
    """Тёмный кадр не доходит до распознавания, но виден в статистике."""
    sp, pipe = _make()
    sp.process(_frame(_dark_image()))
    assert pipe.process_calls == 0  # OCR не звали
    assert sp.frames_dropped == 1
    assert sp.frames_seen == 1


def test_good_frame_goes_to_ocr():
    sp, pipe = _make()
    pipe.next = _det("127AST02", 0)
    sp.process(_frame(_good_image()))
    assert pipe.process_calls == 1
    assert sp.frames_dropped == 0


def test_event_not_lost_when_car_leaves_on_bad_frames():
    """Машина уехала на серии плохих кадров — событие всё равно эмитится.

    Это главный риск фикса: если плохой кадр просто пропускать, трек не состарится
    и проезд потеряется. Плохой кадр = кадр без детекций → трек стареет как обычно.
    """
    sp, pipe = _make()
    # машина проезжает на нормальных кадрах
    for i in range(6):
        pipe.next = _det("127AST02", i)
        assert sp.process(_frame(_good_image(), i)) == []
    # затем свет пропал/смазало — идут плохие кадры, машина уже уехала
    pipe.next = None
    emitted: list[dict] = []
    for i in range(GAP_LEN):
        emitted += sp.process(_frame(_dark_image(), 100 + i))

    assert len(emitted) == 1  # событие не потерялось
    assert emitted[0]["plate_number"] == "127AST02"
    assert sp.frames_dropped == GAP_LEN


def test_bad_frames_do_not_break_ongoing_track():
    """Кратковременная засветка/смаз в середине проезда не рвёт трек на два события."""
    sp, pipe = _make()
    for i in range(4):
        pipe.next = _det("127AST02", i)
        sp.process(_frame(_good_image(), i))
    # два плохих кадра подряд (в пределах max_age)
    pipe.next = None
    for i in range(2):
        sp.process(_frame(_dark_image(), 50 + i))
    # машина снова видна
    for i in range(4, 8):
        pipe.next = _det("127AST02", i)
        sp.process(_frame(_good_image(), i))

    pipe.next = None
    emitted: list[dict] = []
    for i in range(GAP_LEN):
        emitted += sp.process(_frame(_dark_image(), 200 + i))

    assert len(emitted) == 1  # один проезд — одно событие
