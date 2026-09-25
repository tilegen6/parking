"""Конфигурация распознавателя (мапится на CLI-флаги recognize.py)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecognizerConfig:
    engine: str = "template"  # template | easyocr | fastplate (спец. OCR номеров)
    detector: str = "whole"  # whole | yolo | plate (plate = open-image-models, лучший)
    plate_model: str | None = None  # путь к YOLO-модели (или авто-скачивание)
    direction: str = "unknown"  # entry | exit | unknown
    camera_name: str | None = None
    confidence_threshold: float = 0.85  # ТЗ 2.4

    # видео
    video_fps: float = 5.0  # сколько кадров/сек выбирать из видео (ТЗ 2.1: 3-10)
    vote_window_seconds: float = 3.0  # окно majority-vote по треку

    # живой поток (StreamPipeline)
    min_hits: int = 3  # минимум кадров в треке, чтобы эмитить событие
    cooldown_seconds: float = 60.0  # анти-повтор: не слать тот же номер чаще

    # трекинг в живом потоке. Считаем в СЕКУНДАХ, а не в кадрах: реальный шаг
    # кадра плавает (инференс, реконнект), и «5 кадров» — это то 1 с, то 5 с.
    track_max_age_seconds: float = 1.5  # сколько трек живёт без новых попаданий
    track_iou: float = 0.3  # порог ассоциации бокса с треком
    track_reacquire_iou: float = 0.1  # мягкий порог для трека, потерявшего бокс

    # фильтр качества (ТЗ 2.1)
    blur_threshold: float = 100.0  # var of Laplacian ниже -> смазано
    dark_threshold: float = 40.0  # средняя яркость ниже -> темно

    # вывод (относительно текущей директории запуска)
    out_dir: str = "out"
    annotate: bool = False
    send_to_backend: str | None = None  # URL backend или None
