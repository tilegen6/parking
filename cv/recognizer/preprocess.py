"""Препроцесс crop пластины перед OCR (ТЗ 2.2): gray, contrast, denoise, sharpen."""

from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]


def preprocess_plate(image: np.ndarray) -> np.ndarray:
    """Подготовить изображение пластины к OCR. Без cv2 — возвращает как есть."""
    if cv2 is None:
        return image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    sharp = cv2.addWeighted(gray, 1.5, blur, -0.5, 0)
    return sharp
