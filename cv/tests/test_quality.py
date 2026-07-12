"""Тесты фильтра качества (numpy-only, без cv2)."""

import numpy as np

from recognizer.quality import frame_ok, is_blurry, is_dark


def _checkerboard(size=60):
    idx = np.add.outer(np.arange(size), np.arange(size))
    return ((idx % 2) * 255).astype(np.uint8)


def test_uniform_image_is_blurry():
    flat = np.full((60, 60), 200, dtype=np.uint8)  # нет деталей -> "смазано"
    assert is_blurry(flat)


def test_high_frequency_image_is_sharp():
    assert not is_blurry(_checkerboard())


def test_dark_image_detected():
    dark = np.full((60, 60), 10, dtype=np.uint8)
    assert is_dark(dark)


def test_bright_image_not_dark():
    bright = np.full((60, 60), 180, dtype=np.uint8)
    assert not is_dark(bright)


def test_frame_ok_combines():
    good = _checkerboard()  # резко и не темно
    assert frame_ok(good)
    assert not frame_ok(np.full((60, 60), 5, dtype=np.uint8))  # темно
    assert not frame_ok(np.full((60, 60), 200, dtype=np.uint8))  # смазано
