"""Фильтр качества кадра (ТЗ 2.1): отсев смазанных и тёмных.

Считаем без cv2/scipy (чистый numpy), чтобы модуль и его тесты не тянули тяжёлые
зависимости.
"""

from __future__ import annotations

import numpy as np


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return image[..., :3].mean(axis=2).astype(float)
    return image.astype(float)


def laplacian_variance(image: np.ndarray) -> float:
    """Вариация лапласиана — мера резкости (ниже = более смазано)."""
    gray = _to_gray(image)
    h, w = gray.shape
    if h < 3 or w < 3:
        return 0.0
    # лапласиан 4-связности: N + S + E + W - 4*center (valid-область)
    lap = (
        gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
        - 4 * gray[1:-1, 1:-1]
    )
    return float(lap.var())


def mean_brightness(image: np.ndarray) -> float:
    return float(_to_gray(image).mean())


def is_blurry(image: np.ndarray, threshold: float = 100.0) -> bool:
    return laplacian_variance(image) < threshold


def is_dark(image: np.ndarray, threshold: float = 40.0) -> bool:
    return mean_brightness(image) < threshold


def frame_ok(
    image: np.ndarray, blur_threshold: float = 100.0, dark_threshold: float = 40.0
) -> bool:
    return not is_blurry(image, blur_threshold) and not is_dark(image, dark_threshold)
