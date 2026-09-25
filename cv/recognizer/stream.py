"""Онлайн-эмиссия событий из живого потока (RTSP/телефон/файл).

`run_video` собирает события в конце файла — для бесконечного потока так нельзя.
`StreamPipeline` работает покадрово и эмитит событие в момент **закрытия трека**
(машина ушла из кадра: трек состарился на max_age кадров), если трек набрал
достаточно кадров и majority-vote дал номер. Кулдаун по номеру гасит повторы
(мигание, остановка на линии).

Перед распознаванием кадр проходит фильтр качества (смаз/темнота): мусорные
чтения портят голосование. Отбракованный кадр не отменяет старение треков —
иначе машина, уехавшая на серии плохих кадров, не «закрылась» бы вовсе.

Один проезд = ровно одно событие. Направление берётся из конфига потока
(топология: камера въезда / камера выезда).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import RecognizerConfig
from .normalize import normalize_plate
from .pipeline import FrameResult
from .quality import frame_ok
from .track import SimpleTracker
from .vote import MajorityVote


@dataclass
class _TrackState:
    vote: MajorityVote = field(default_factory=MajorityVote)
    hits: int = 0
    last_frame: object = None  # последний Frame трека
    last_res: FrameResult | None = None


class StreamPipeline:
    """Покадровый распознаватель потока с эмиссией на закрытии трека.

    `pipeline` — объект с методами `process_frame(image) -> FrameResult|None` и
    `_emit(res, frame, sinks) -> dict|None` (боевой — recognizer.pipeline.Pipeline).
    `clock` — источник монотонного времени в секундах (для кулдауна; в тестах
    подменяется).
    """

    def __init__(
        self,
        pipeline,  # noqa: ANN001 — Pipeline или совместимый (см. docstring)
        cfg: RecognizerConfig,
        sinks: dict | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.cfg = cfg
        self.sinks = sinks or {}
        self._clock = clock or time.monotonic
        self.tracker = SimpleTracker(
            iou_threshold=cfg.track_iou,
            max_age_seconds=cfg.track_max_age_seconds,
            reacquire_iou=cfg.track_reacquire_iou,
        )
        self._tracks: dict[int, _TrackState] = {}
        self._cooldown: dict[str, float] = {}

        # наблюдаемость (для /stream/status и /stream/preview)
        self.frames_seen = 0
        self.events_emitted = 0
        self.frames_dropped = 0  # отсеяно фильтром качества (смаз/темнота)
        self.last_frame: object = None
        self.last_res: FrameResult | None = None
        self.last_plate: str | None = None

    def _read_frame(self, image) -> list[FrameResult]:  # noqa: ANN001
        """Все номера кадра. Пайплайн без `process_frame_multi` — как один номер.

        Фолбэк нужен, потому что контракт `pipeline` объявлен в докстринге класса
        и используется тестовыми дублями; молча ломать его нельзя.
        """
        multi = getattr(self.pipeline, "process_frame_multi", None)
        if callable(multi):
            return list(multi(image))
        res = self.pipeline.process_frame(image)
        return [res] if res else []

    def process(self, frame) -> list[dict]:  # noqa: ANN001
        """Обработать один кадр; вернуть события, эмитнутые на этом кадре."""
        self.frames_seen += 1
        now = self._clock()

        # Фильтр качества (ТЗ 2.1): смазанные и тёмные кадры не гоним в OCR —
        # мусорные чтения искажают голосование именно ночью и в движении.
        # ВАЖНО: трекер всё равно обновляем — иначе треки не стареют, и машина,
        # уехавшая на серии плохих кадров, никогда не «закроется» (событие
        # потеряется совсем). Плохой кадр = кадр без детекций, не пауза.
        if not frame_ok(frame.image, self.cfg.blur_threshold, self.cfg.dark_threshold):
            self.frames_dropped += 1
            self.last_frame = frame
            self.tracker.update([], now)
            return self._collect_closed()

        results = [r for r in self._read_frame(frame.image) if r and r.plate]
        self.last_frame = frame
        # Для превью показываем самое уверенное чтение кадра.
        best = max(results, key=lambda r: r.confidence, default=None)
        self.last_res = best
        if best is not None:
            self.last_plate = best.plate

        h, w = frame.image.shape[:2]
        boxes = [r.box or (0, 0, w, h) for r in results]
        # Все номера кадра идут в трекер разом: иначе стоящая у стрелы машина и
        # подъезжающая за ней делят один трек, и их чтения смешиваются в общем
        # голосовании — отсюда «открыли не тому».
        tids = self.tracker.update(boxes, now)
        for tid, res in zip(tids, results, strict=False):
            st = self._tracks.setdefault(tid, _TrackState())
            st.vote.add(res.plate, res.confidence)
            st.hits += 1
            st.last_frame = frame
            st.last_res = res

        return self._collect_closed()

    def _collect_closed(self) -> list[dict]:
        """Эмитим треки, которые только что выпали из активных (машина уехала)."""
        active = {t.track_id for t in self.tracker.active}
        closed = [tid for tid in self._tracks if tid not in active]
        out = []
        for tid in closed:
            rec = self._emit_track(self._tracks.pop(tid))
            if rec:
                out.append(rec)
        return out

    def flush(self) -> list[dict]:
        """Закрыть все открытые треки (вызывать на остановке потока)."""
        out = []
        for tid in list(self._tracks):
            rec = self._emit_track(self._tracks.pop(tid))
            if rec:
                out.append(rec)
        return out

    def _emit_track(self, st: _TrackState) -> dict | None:
        if st.hits < self.cfg.min_hits:
            return None
        vr = st.vote.result()
        if not vr or not vr.plate:
            return None

        now = self._clock()
        prev = self._cooldown.get(vr.plate)
        if prev is not None and (now - prev) < self.cfg.cooldown_seconds:
            return None  # тот же номер недавно уже отправляли
        self._cooldown[vr.plate] = now

        voted = FrameResult(
            plate=vr.plate,
            confidence=vr.confidence,
            box=st.last_res.box if st.last_res else None,
            is_valid=normalize_plate(vr.plate).is_valid,
            alts=st.last_res.alts if st.last_res else [],
        )
        rec = self.pipeline._emit(voted, st.last_frame, self.sinks)
        if rec:
            self.events_emitted += 1
        return rec
