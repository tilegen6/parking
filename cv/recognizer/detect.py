"""Детекция региона пластины (ТЗ 2.2, «Этап 1»).

Интерфейс PlateDetector отделяет локализацию от OCR:
- WholeFrameDetector — отдаёт весь кадр как один регион. Подходит для синтетики
  (изображение и есть пластина) и для EasyOcr, который локализует текст сам.
- YoloPlateDetector — находит на кадре прямоугольник номера (YOLOv8) и отдаёт
  вырезанный кроп. Нужен на «грязных» полнокадровых фото/видео: OCR читает только
  пластину, а не весь текст сцены.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

# Готовая pretrained-модель детекции номеров (YOLOv8). Авто-скачивается при первом
# использовании. Позже заменяется дообученной на казахстанских номерах (Roboflow/CVAT).
PLATE_MODEL_URL = (
    "https://huggingface.co/Koushim/yolov8-license-plate-detection/resolve/main/best.pt"
)


@dataclass
class Region:
    image: np.ndarray
    box: tuple[int, int, int, int] | None = None  # координаты в исходном кадре


class PlateDetector(ABC):
    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Region]: ...


class WholeFrameDetector(PlateDetector):
    def detect(self, frame: np.ndarray) -> list[Region]:
        return [Region(frame, None)]


def default_model_path() -> str:
    return os.path.join(os.path.dirname(__file__), "models", "license_plate.pt")


def ensure_plate_model(path: str | None = None) -> str:
    """Вернуть путь к модели, скачав её при отсутствии."""
    path = path or os.environ.get("CV_PLATE_MODEL") or default_model_path()
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    from .util import ensure_ssl_certs

    ensure_ssl_certs()
    import urllib.request

    print(f"Скачиваю модель детекции номеров -> {path} ...")
    urllib.request.urlretrieve(PLATE_MODEL_URL, path)
    return path


class YoloPlateDetector(PlateDetector):
    """Детекция пластины YOLOv8: возвращает кропы найденных номеров."""

    def __init__(
        self,
        model_path: str | None = None,
        conf: float = 0.25,
        padding: float = 0.08,
    ) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise RuntimeError(
                "ultralytics не установлен. `pip install ultralytics` "
                "или используйте --detector whole"
            ) from e
        self.conf = conf
        self.padding = padding
        self._model = YOLO(ensure_plate_model(model_path))

    def detect(self, frame: np.ndarray) -> list[Region]:
        results = self._model.predict(frame, conf=self.conf, verbose=False)
        h, w = frame.shape[:2]
        regions: list[tuple[float, Region]] = []
        for res in results:
            boxes = res.boxes
            if boxes is None:
                continue
            for box in boxes:  # type: ignore[attr-defined]  # Boxes итерируем в рантайме
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                score = float(box.conf[0]) if box.conf is not None else 0.0
                pad_x = (x2 - x1) * self.padding
                pad_y = (y2 - y1) * self.padding
                ix1 = max(0, int(x1 - pad_x))
                iy1 = max(0, int(y1 - pad_y))
                ix2 = min(w, int(x2 + pad_x))
                iy2 = min(h, int(y2 + pad_y))
                crop = frame[iy1:iy2, ix1:ix2]
                if crop.size:
                    regions.append((score, Region(crop, (ix1, iy1, ix2, iy2))))
        # самые уверенные детекции первыми
        regions.sort(key=lambda t: t[0], reverse=True)
        return [r for _, r in regions]
