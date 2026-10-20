"""Оркестратор пайплайна распознавания.

Картинки: каждое изображение -> независимое событие.
Видео: трекинг + majority-vote по треку -> одно событие на трек.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .config import RecognizerConfig
from .events import build_event, normalize_direction
from .kz_format import normalize_kz
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
    plate_raw: str | None = None
    normalization_status: str | None = None


def make_detector(cfg: RecognizerConfig):
    if cfg.detector == "plate":
        from .detect import OpenImagePlateDetector

        return OpenImagePlateDetector()
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
    if cfg.engine == "fastplate":
        from .ocr import FastPlateOcr

        return FastPlateOcr()
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
            norm = normalize_kz(r.text, r.char_confidences)
            box = region_box if region_box is not None else r.box
            scored.append(
                (
                    norm.is_trusted,
                    plate_likeness(r.text),
                    r.confidence,
                    FrameResult(
                        plate=norm.plate,
                        confidence=r.confidence,
                        box=box,
                        is_valid=norm.is_trusted,
                        plate_raw=r.text,
                        normalization_status=norm.status,
                    ),
                )
            )
        if not scored:
            return None
        scored.sort(key=lambda t: (t[0], round(t[1], 1), t[2]), reverse=True)
        result = scored[0][3]
        result.alts = [t[3].plate for t in scored[:5] if t[3].plate]
        return result

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
        last: dict[int, dict[str, tuple]] = {}
        for frame in source.frames():
            # фильтр качества (ТЗ 2.1) — только для видеопотока
            if not frame_ok(
                frame.image, self.cfg.blur_threshold, self.cfg.dark_threshold
            ):
                continue
            res = self.process_frame(frame.image)
            h, w = frame.image.shape[:2]
            # трекер обновляется на КАЖДОМ обработанном кадре — иначе max_age
            # считается по детекциям, а не по кадрам, и две машины через серию
            # «пустых» кадров сольются в один трек.
            if res and res.plate:
                box = res.box or (0, 0, w, h)
                tid = tracker.update([box])[0]
                votes.setdefault(tid, MajorityVote()).add(res.plate, res.confidence)
                last.setdefault(tid, {})[res.plate] = (frame, res)
            else:
                tracker.update([])  # старим треки на кадре без номера

        events = []
        for tid, vote in votes.items():
            vr = vote.result()
            if not vr:
                continue
            frame, res = last[tid][vr.plate]
            voted = replace(res, confidence=vr.confidence)
            rec = self._emit(voted, frame, sinks)
            if rec:
                events.append(rec)
        return events

    def _emit(self, res: FrameResult | None, frame, sinks: dict) -> dict | None:
        if res is None:
            return None
        below = res.confidence < self.cfg.confidence_threshold
        flag = "ok" if (res.is_valid and not below) else "low_confidence"
        norm_status = res.normalization_status
        if norm_status is None or (
            not res.is_valid and norm_status in ("ok", "corrected")
        ):
            norm_status = "ok" if res.is_valid else "unknown_format"
        event = build_event(
            plate_number=res.plate or None,
            direction=normalize_direction(self.cfg.direction),
            confidence=round(res.confidence, 3),
            camera_name=self.cfg.camera_name or frame.source_name,
            event_time=frame.timestamp,
            plate_raw=res.plate_raw,
            normalization_status=norm_status,
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
