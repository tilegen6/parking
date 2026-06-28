"""Детекция региона пластины (ТЗ 2.2, «Этап 1»).

Интерфейс PlateDetector отделяет локализацию от OCR. Для MVP:
- WholeFrameDetector — отдаёт весь кадр как один регион. Подходит для синтетики
  (изображение и есть пластина) и для EasyOcr, который локализует текст сам.

Будущий `YoloPlateDetector` подключается как ещё одна реализация интерфейса,
не трогая пайплайн.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


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
