"""Движки OCR за единым интерфейсом PlateOcr.

- TemplateOcr — детерминированный template-matching по тому же шрифту, что у synth.
  Нужен только cv2 (без torch). Используется для офлайн-тестов/демо.
- EasyOcr — реальный движок для фото (тянет torch). Опционален.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]


@dataclass
class OcrResult:
    text: str
    confidence: float
    box: tuple[int, int, int, int] | None = None  # x1, y1, x2, y2


class PlateOcr(ABC):
    @abstractmethod
    def read(self, image: np.ndarray) -> list[OcrResult]:
        """Прочитать текст(ы) с изображения региона/кадра."""


# --------------------------- TemplateOcr (синтетика) ---------------------------

_TPL_H, _TPL_W = 48, 32


class TemplateOcr(PlateOcr):
    """Сегментация по столбцам + сопоставление символов с шаблонами шрифта."""

    def __init__(self) -> None:
        if cv2 is None:
            raise RuntimeError("TemplateOcr требует opencv-python (cv2)")
        from . import synth

        self._templates: dict[str, np.ndarray] = {
            ch: self._norm(synth.render_glyph(ch))
            for ch in synth.LETTERS + synth.DIGITS
        }

    def _norm(self, gray: np.ndarray) -> np.ndarray:
        r = cv2.resize(gray, (_TPL_W, _TPL_H), interpolation=cv2.INTER_AREA).astype(
            float
        )
        r = r - r.mean()
        n = float(np.linalg.norm(r))
        return r / n if n > 0 else r

    def _segment(self, image: np.ndarray) -> list[np.ndarray]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        _, binimg = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        col_ink = binimg.sum(axis=0)
        spans: list[tuple[int, int]] = []
        in_char = False
        start = 0
        for x, v in enumerate(col_ink):
            if v > 0 and not in_char:
                in_char, start = True, x
            elif v == 0 and in_char:
                in_char = False
                if x - start >= 3:
                    spans.append((start, x))
        if in_char and len(col_ink) - start >= 3:
            spans.append((start, len(col_ink)))

        crops: list[np.ndarray] = []
        for x1, x2 in spans:
            col = binimg[:, x1:x2]
            rows = np.where(col.sum(axis=1) > 0)[0]
            if len(rows) == 0:
                continue
            crops.append(gray[rows.min() : rows.max() + 1, x1:x2])
        return crops

    def read(self, image: np.ndarray) -> list[OcrResult]:
        chars: list[str] = []
        scores: list[float] = []
        for crop in self._segment(image):
            t = self._norm(crop)
            best_ch, best_score = "", -1.0
            for ch, tpl in self._templates.items():
                s = float((t * tpl).sum())  # нормированная корреляция в [-1, 1]
                if s > best_score:
                    best_ch, best_score = ch, s
            chars.append(best_ch)
            scores.append(max(0.0, min(1.0, best_score)))
        if not chars:
            return []
        return [OcrResult("".join(chars), sum(scores) / len(scores))]


def _upscale_small(image: np.ndarray, min_height: int = 64, max_scale: float = 4.0):
    """Увеличить мелкий кроп пластины — EasyOCR читает крупный текст точнее."""
    if cv2 is None or image.ndim < 2:
        return image
    h = image.shape[0]
    if h >= min_height or h == 0:
        return image
    scale = min(max_scale, min_height / h)
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


# ------------------------------ EasyOcr (реальное) -----------------------------


class EasyOcr(PlateOcr):
    def __init__(
        self, languages: tuple[str, ...] = ("en",), preprocess: bool = False
    ) -> None:
        from .util import ensure_ssl_certs

        ensure_ssl_certs()
        try:
            import easyocr
        except ImportError as e:
            raise RuntimeError(
                "EasyOCR не установлен. `pip install easyocr` "
                "или используйте --engine template"
            ) from e
        self._preprocess = None
        if preprocess:
            from .preprocess import preprocess_plate

            self._preprocess = preprocess_plate
        self._reader = easyocr.Reader(list(languages), gpu=False, verbose=False)

    def read(self, image: np.ndarray) -> list[OcrResult]:
        prepared = self._preprocess(image) if self._preprocess else image
        prepared = _upscale_small(prepared)
        results: list[OcrResult] = []
        for box, text, conf in self._reader.readtext(prepared):
            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            results.append(
                OcrResult(text, float(conf), (min(xs), min(ys), max(xs), max(ys)))
            )
        return results
