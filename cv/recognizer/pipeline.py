"""Оркестратор пайплайна распознавания.

Картинки: каждое изображение -> независимое событие.
Видео: трекинг + majority-vote по треку -> одно событие на трек.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import RecognizerConfig
from .events import build_event, normalize_direction
from .normalize import normalize_plate
from .quality import frame_ok
from .vote import MajorityVote

_ALNUM = re.compile(r"[^A-Z0-9]")


def plate_likeness(text: str) -> float:
    """Эвристика «похоже на автономер»: длина 4-9, смесь букв и цифр.

    Нужна, чтобы на реальном фото выбрать номер, а не название региона/слоган.
    """
    c = _ALNUM.sub("", (text or "").upper())
    n = len(c)
    if not (4 <= n <= 9):
        return 0.0
    has_digit = any(ch.isdigit() for ch in c)
    has_alpha = any(ch.isalpha() for ch in c)
    score = 0.6 if (has_digit and has_alpha) else 0.2
    if 6 <= n <= 8:
        score += 0.4
    elif n in (5, 9):
        score += 0.2
    return min(1.0, score)


@dataclass
class FrameResult:
    plate: str  # нормализованный (или очищенный) текст
    confidence: float
    box: tuple[int, int, int, int] | None
    is_valid: bool  # прошёл ли формат KZ
    alts: list[str] = field(default_factory=list)  # прочие распознанные тексты


def make_detector(cfg: RecognizerConfig):
    if cfg.detector == "yolo":
        from .detect import YoloPlateDetector

        return YoloPlateDetector(cfg.plate_model)
    from .detect import WholeFrameDetector

    return WholeFrameDetector()


def make_ocr(cfg: RecognizerConfig):
    if cfg.engine == "template":
        from .ocr import TemplateOcr

        return TemplateOcr()
    if cfg.engine == "easyocr":
        from .ocr import EasyOcr

        return EasyOcr()
    raise ValueError(f"Неизвестный движок OCR: {cfg.engine}")


class Pipeline:
    def __init__(self, cfg: RecognizerConfig, detector=None, ocr=None) -> None:
        self.cfg = cfg
        self.detector = detector or make_detector(cfg)
        self.ocr = ocr or make_ocr(cfg)

    def _best(self, candidates) -> FrameResult | None:
        """Выбрать кандидата: валидный формат -> похоже-на-номер -> confidence.

        candidates: список (OcrResult, region_box). Для рамки берём абсолютный бокс —
        region_box (бокс региона детектора в координатах кадра), иначе бокс OCR.
        """
        scored = []
        for r, region_box in candidates:
            norm = normalize_plate(r.text)
            box = region_box if region_box is not None else r.box
            scored.append(
                (
                    norm.is_valid,
                    plate_likeness(r.text),
                    r.confidence,
                    norm.normalized,
                    box,
                )
            )
        if not scored:
            return None
        scored.sort(key=lambda t: (t[0], round(t[1], 1), t[2]), reverse=True)
        is_valid, _like, conf, plate, box = scored[0]
        alts = [t[3] for t in scored[:5] if t[3]]
        return FrameResult(
            plate=plate, confidence=conf, box=box, is_valid=is_valid, alts=alts
        )

    def process_frame(self, image) -> FrameResult | None:
        candidates = []
        for region in self.detector.detect(image):
            for r in self.ocr.read(region.image):
                candidates.append((r, region.box))
        return self._best(candidates)

    def run_images(self, source, sinks: dict) -> list[dict]:
        events = []
        for frame in source.frames():
            res = self.process_frame(frame.image)
            rec = self._emit(res, frame, sinks)
            if rec:
                events.append(rec)
        return events

    def run_video(self, source, sinks: dict) -> list[dict]:
        from .track import SimpleTracker

        tracker = SimpleTracker()
        votes: dict[int, MajorityVote] = {}
        last: dict[int, tuple] = {}
        for frame in source.frames():
            # фильтр качества (ТЗ 2.1) — только для видеопотока
            if not frame_ok(
                frame.image, self.cfg.blur_threshold, self.cfg.dark_threshold
            ):
                continue
            res = self.process_frame(frame.image)
            if not res or not res.plate:
                continue
            h, w = frame.image.shape[:2]
            box = res.box or (0, 0, w, h)
            tid = tracker.update([box])[0]
            votes.setdefault(tid, MajorityVote()).add(res.plate, res.confidence)
            last[tid] = (frame, res)

        events = []
        for tid, vote in votes.items():
            vr = vote.result()
            if not vr:
                continue
            frame, res = last[tid]
            voted = FrameResult(
                plate=vr.plate,
                confidence=vr.confidence,
                box=res.box,
                is_valid=normalize_plate(vr.plate).is_valid,
                alts=res.alts,
            )
            rec = self._emit(voted, frame, sinks)
            if rec:
                events.append(rec)
        return events

    def _emit(self, res: FrameResult | None, frame, sinks: dict) -> dict | None:
        if res is None:
            return None
        below = res.confidence < self.cfg.confidence_threshold
        flag = "ok" if (res.is_valid and not below) else "low_confidence"
        event = build_event(
            plate_number=res.plate or None,
            direction=normalize_direction(self.cfg.direction),
            confidence=round(res.confidence, 3),
            camera_name=self.cfg.camera_name or frame.source_name,
            event_time=frame.timestamp,
        )
        contract = event.to_contract()
        record = {
            **contract,
            "flag": flag,
            "frame": frame.source_name,
            "candidates": res.alts,
        }

        for s in sinks.get("json", []):
            s.write(record)
        for s in sinks.get("annot", []):
            s.write(frame.image, event.plate_number, res.box)
        for s in sinks.get("backend", []):
            try:
                record["backend_response"] = s.send(event.to_backend_json())
            except Exception as e:  # noqa: BLE001
                record["backend_error"] = str(e)
        return record
