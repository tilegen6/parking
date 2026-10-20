"""Normalisation safety must survive the real pipeline and aggregation paths."""

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from recognizer.config import RecognizerConfig
from recognizer.detect import Region
from recognizer.ocr import FastPlateOcr, OcrResult
from recognizer.pipeline import FrameResult, Pipeline
from recognizer.sources import Frame
from recognizer.stream import StreamPipeline


def make_pipe(text, confidences=None):
    result = OcrResult(text, 0.99)
    result.char_confidences = confidences
    detector = SimpleNamespace(detect=lambda image: [Region(image)])
    ocr = SimpleNamespace(read=lambda image: [result])
    return Pipeline(
        RecognizerConfig(direction="entry", blur_threshold=0, dark_threshold=0),
        detector,
        ocr,
    )


def frame():
    return Frame(
        np.zeros((10, 10, 3), dtype=np.uint8),
        0,
        datetime.now(timezone.utc),
        "synthetic",
    )


@pytest.mark.parametrize(
    "text,confidences,valid,plate",
    [
        ("AQ00301", None, True, "AQ00301"),
        ("237BLM99", None, False, "237BLM99"),
        ("237BLMO1", [0.99] * 8, False, "237BLMO1"),
        ("237BLMO1", [0.99] * 6 + [0.5, 0.99], True, "237BLM01"),
    ],
)
def test_pipeline_uses_extended_kz_rules(text, confidences, valid, plate):
    result = make_pipe(text, confidences).process_frame(frame().image)
    assert result.is_valid is valid
    assert result.plate == plate


def test_fastplate_preserves_symbol_confidence():
    ocr = FastPlateOcr.__new__(FastPlateOcr)
    probs = np.array([0.99] * 6 + [0.4, 0.99])
    ocr._ocr = SimpleNamespace(
        run=lambda *args, **kwargs: [
            SimpleNamespace(plate="237BLMO1", char_probs=probs)
        ]
    )
    result = ocr.read(frame().image)[0]
    assert result.char_confidences == pytest.approx(probs.tolist())


@pytest.mark.parametrize("path", ["image", "video", "stream"])
def test_untrusted_format_stays_untrusted_after_aggregation(path):
    pipe = make_pipe("237BLMO1", [0.99] * 8)
    source = SimpleNamespace(frames=lambda: iter([frame()] * 3))
    if path == "image":
        events = pipe.run_images(source, {})
    elif path == "video":
        events = pipe.run_video(source, {})
    else:
        stream = StreamPipeline(pipe, pipe.cfg)
        for _ in range(3):
            stream.process(frame())
        events = stream.flush()
    assert events
    assert all(e["flag"] == "low_confidence" for e in events)
    assert all(e["normalization_status"] == "unknown_format" for e in events)
    assert all(e["plate_raw"] == "237BLMO1" for e in events)


def test_backend_payload_carries_normalisation_decision():
    received = []
    sink = SimpleNamespace(send=lambda payload: received.append(payload))
    pipe = make_pipe("237BLMO1", [0.99] * 8)
    pipe.run_images(
        SimpleNamespace(frames=lambda: iter([frame()])), {"backend": [sink]}
    )
    assert received[0]["normalizationStatus"] == "unknown_format"
    assert received[0]["plateRaw"] == "237BLMO1"
    assert received[0]["confidence"] == 0.99


def test_legacy_untrusted_frame_is_not_sent_as_trusted():
    received = []
    sink = SimpleNamespace(send=lambda payload: received.append(payload))
    pipe = make_pipe("123ABC02")
    pipe._emit(
        FrameResult("bad-plate", 0.99, None, False), frame(), {"backend": [sink]}
    )
    assert received[0]["normalizationStatus"] == "unknown_format"
