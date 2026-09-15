"""Генератор синтетических KZ-номеров для офлайн-тестов и демо.

Рисует чистую пластину фиксированным шрифтом Hershey (тот же, что использует
TemplateOcr) с равными промежутками между символами — чтобы сегментация по
столбцам работала детерминированно. Можно добавить шум/блюр.

Имя файла сгенерированной пластины = сам номер (ground truth для e2e-теста).
"""

from __future__ import annotations

import os
import random

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

FONT_SCALE = 2.0
THICKNESS = 3
CHAR_GAP = 16  # пиксели между символами (гарантируют пустые столбцы для сегментации)
MARGIN = 24
PLATE_H = 130

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError("Для синтетики нужен opencv-python (cv2)")


def random_kz_plate(rng: random.Random | None = None) -> str:
    r = rng or random
    fmt = r.choice(["DDDLLLDD", "LDDDLLL"])
    return "".join(r.choice(DIGITS if cls == "D" else LETTERS) for cls in fmt)


def _tight_crop(gray: np.ndarray) -> np.ndarray:
    ys, xs = np.where(gray < 128)
    if len(xs) == 0:
        return gray
    return gray[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def render_glyph(ch: str) -> np.ndarray:
    """Один чёрный символ на белом, плотно обрезанный (шаблон для TemplateOcr)."""
    _require_cv2()
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), baseline = cv2.getTextSize(ch, font, FONT_SCALE, THICKNESS)
    canvas = np.full((h + baseline + 12, w + 12), 255, dtype=np.uint8)
    cv2.putText(canvas, ch, (6, h + 6), font, FONT_SCALE, 0, THICKNESS, cv2.LINE_AA)
    return _tight_crop(canvas)


def render_plate(text: str, noise: float = 0.0, blur: int = 0) -> np.ndarray:
    """Пластина: белый фон, чёрные символы с равными промежутками (BGR)."""
    _require_cv2()
    font = cv2.FONT_HERSHEY_SIMPLEX
    sizes = [cv2.getTextSize(ch, font, FONT_SCALE, THICKNESS)[0] for ch in text]
    total_w = sum(w for w, _ in sizes) + CHAR_GAP * (len(text) - 1) + 2 * MARGIN
    plate = np.full((PLATE_H, total_w), 255, dtype=np.uint8)
    x = MARGIN
    baseline_y = PLATE_H // 2 + 32
    for ch, (w, _) in zip(text, sizes):
        cv2.putText(
            plate, ch, (x, baseline_y), font, FONT_SCALE, 0, THICKNESS, cv2.LINE_AA
        )
        x += w + CHAR_GAP
    img = cv2.cvtColor(plate, cv2.COLOR_GRAY2BGR)
    if blur > 0:
        k = blur * 2 + 1
        img = cv2.GaussianBlur(img, (k, k), 0)
    if noise > 0:
        n = np.random.normal(0, noise * 255, img.shape)
        img = np.clip(img.astype(float) + n, 0, 255).astype(np.uint8)
    return img


def generate_dataset(
    out_dir: str, n: int = 12, seed: int | None = 42, noise: float = 0.0, blur: int = 0
) -> list[str]:
    """Сгенерировать n уникальных пластин. Имя файла = номер. Вернуть пути."""
    _require_cv2()
    rng = random.Random(seed)
    if seed is not None:
        np.random.seed(seed)
    os.makedirs(out_dir, exist_ok=True)
    paths: list[str] = []
    seen: set[str] = set()
    while len(paths) < n:
        plate = random_kz_plate(rng)
        if plate in seen:
            continue
        seen.add(plate)
        img = render_plate(plate, noise=noise, blur=blur)
        path = os.path.join(out_dir, f"{plate}.png")
        cv2.imwrite(path, img)
        paths.append(path)
    return paths
