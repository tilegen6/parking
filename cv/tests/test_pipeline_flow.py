"""Связка детектор -> OCR -> выбор кандидата (без cv2/YOLO/EasyOCR).

Проверяет, что регионы от детектора прогоняются через OCR и выбирается лучший
кандидат (валидный KZ-номер важнее текста с большей confidence).
"""

import numpy as np

from recognizer.config import RecognizerConfig
from recognizer.detect import Region
from recognizer.ocr import OcrResult
from recognizer.pipeline import Pipeline


class _FakeDetector:
    def __init__(self, regions):
        self._regions = regions

    def detect(self, frame):
        return self._regions


class _FakeOcr:
    """Читает «номер» региона по значению пикселя [0,0] (детерминированно)."""

    def __init__(self, mapping):
        self._mapping = mapping

    def read(self, image):
        return self._mapping.get(int(image[0, 0]), [])


def _marker(value):
    a = np.zeros((2, 2), dtype=int)
    a[0, 0] = value
    return a


def test_detector_regions_feed_ocr_and_best_selected():
    junk, plate = _marker(1), _marker(2)
    detector = _FakeDetector([Region(junk), Region(plate)])
    ocr = _FakeOcr(
        {
            1: [OcrResult("POLICE", 0.99)],  # мусор, высокая conf
            2: [OcrResult("127AST02", 0.80)],  # валидный KZ, ниже conf
        }
    )
    cfg = RecognizerConfig(engine="template")  # движки внедрены, не создаются
    pipe = Pipeline(cfg, detector=detector, ocr=ocr)

    res = pipe.process_frame(np.zeros((4, 4), dtype=int))
    assert res is not None
    assert res.plate == "127AST02"  # валидный формат побеждает большую confidence
    assert res.is_valid
