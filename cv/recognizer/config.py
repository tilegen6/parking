"""Конфигурация распознавателя (мапится на CLI-флаги recognize.py)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecognizerConfig:
    engine: str = "template"  # template | easyocr
    detector: str = "whole"  # whole | yolo (yolo = детекция пластины перед OCR)
    plate_model: str | None = None  # путь к YOLO-модели (или авто-скачивание)
    direction: str = "unknown"  # entry | exit | unknown
    camera_name: str | None = None
    confidence_threshold: float = 0.85  # ТЗ 2.4

    # видео
    video_fps: float = 5.0  # сколько кадров/сек выбирать из видео (ТЗ 2.1: 3-10)
    vote_window_seconds: float = 3.0  # окно majority-vote по треку

    # фильтр качества (ТЗ 2.1)
    blur_threshold: float = 100.0  # var of Laplacian ниже -> смазано
    dark_threshold: float = 40.0  # средняя яркость ниже -> темно

    # вывод (относительно текущей директории запуска)
    out_dir: str = "out"
    annotate: bool = False
    send_to_backend: str | None = None  # URL backend или None
