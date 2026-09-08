"""Адаптеры входа: картинки и видео -> поток Frame.

RTSP-источник добавляется тем же интерфейсом (метод frames()) позже.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class Frame:
    image: np.ndarray
    index: int
    timestamp: datetime
    source_name: str


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError("Нужен opencv-python (cv2) для чтения изображений/видео")


class ImageSource:
    """Один файл или папка с изображениями. Каждое изображение = отдельный кадр."""

    def __init__(self, path: str) -> None:
        _require_cv2()
        if os.path.isdir(path):
            self.files = sorted(
                os.path.join(path, f)
                for f in os.listdir(path)
                if os.path.splitext(f)[1].lower() in IMG_EXT
            )
        else:
            self.files = [path]

    def frames(self) -> Iterator[Frame]:
        for i, f in enumerate(self.files):
            img = cv2.imread(f)
            if img is None:
                continue
            yield Frame(img, i, datetime.now(timezone.utc), os.path.basename(f))


class VideoSource:
    """Видеофайл -> выборка кадров с целевым FPS."""

    def __init__(self, path: str, target_fps: float = 5.0) -> None:
        _require_cv2()
        self.path = path
        self.target_fps = target_fps

    def frames(self) -> Iterator[Frame]:
        cap = cv2.VideoCapture(self.path)
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, int(round(src_fps / max(self.target_fps, 0.1))))
        name = os.path.basename(self.path)
        i = out = 0
        try:
            while True:
                ok, img = cap.read()
                if not ok:
                    break
                if i % step == 0:
                    yield Frame(img, out, datetime.now(timezone.utc), name)
                    out += 1
                i += 1
        finally:
            cap.release()
