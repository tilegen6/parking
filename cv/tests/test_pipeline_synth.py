"""End-to-end на синтетике через TemplateOcr (нужен cv2, не нужен torch/сеть)."""

import os
from datetime import datetime, timezone

import pytest

cv2 = pytest.importorskip("cv2")

from recognizer import synth  # noqa: E402
from recognizer.config import RecognizerConfig  # noqa: E402
from recognizer.normalize import normalize_plate  # noqa: E402
from recognizer.ocr import TemplateOcr  # noqa: E402
from recognizer.pipeline import Pipeline  # noqa: E402
from recognizer.sink import JsonSink  # noqa: E402
from recognizer.sources import Frame, ImageSource  # noqa: E402


def _sinks(out_dir):
    return {"json": [JsonSink(out_dir)], "annot": [], "backend": []}


def test_single_plate_recognized():
    img = synth.render_plate("123ABC01")
    res = TemplateOcr().read(img)
    assert res, "OCR ничего не вернул"
    assert normalize_plate(res[0].text).normalized == "123ABC01"


def test_images_end_to_end(tmp_path):
    in_dir = tmp_path / "in"
    paths = synth.generate_dataset(str(in_dir), n=8, seed=7, blur=0)
    truth = [os.path.splitext(os.path.basename(p))[0] for p in paths]

    cfg = RecognizerConfig(
        engine="template", direction="entry", out_dir=str(tmp_path / "out")
    )
    sinks = _sinks(cfg.out_dir)
    events = Pipeline(cfg).run_images(ImageSource(str(in_dir)), sinks)
    sinks["json"][0].close()

    assert len(events) == len(truth)
    for e in events:
        assert e["direction"] == "ENTRY"
        assert e["source"] == "own-cv-v1"
        assert e["flag"] in {"ok", "low_confidence"}

    recognized = {e["frame"].split(".")[0]: e["plate_number"] for e in events}
    matches = sum(1 for t in truth if recognized.get(t) == t)
    assert matches >= int(0.75 * len(truth)), f"{matches}/{len(truth)}: {recognized}"


class _FakeSource:
    def __init__(self, frames):
        self._frames = frames

    def frames(self):
        yield from self._frames


def test_video_majority_vote(tmp_path):
    img = synth.render_plate("777AAA02")
    frames = [Frame(img, i, datetime.now(timezone.utc), "clip.mp4") for i in range(5)]

    cfg = RecognizerConfig(
        engine="template", direction="exit", out_dir=str(tmp_path / "out")
    )
    sinks = _sinks(cfg.out_dir)
    events = Pipeline(cfg).run_video(_FakeSource(frames), sinks)
    sinks["json"][0].close()

    assert len(events) == 1  # один объект/трек -> одно событие
    assert events[0]["plate_number"] == "777AAA02"
    assert events[0]["direction"] == "EXIT"
