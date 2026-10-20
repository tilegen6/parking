"""Онлайн-эмиссия событий из живого потока (RTSP/телефон/файл).

`run_video` собирает события в конце файла — для бесконечного потока так нельзя.
`StreamPipeline` работает покадрово и эмитит событие в момент **закрытия трека**
(машина ушла из кадра: трек состарился на max_age кадров), если трек набрал
достаточно кадров и majority-vote дал номер. Кулдаун по номеру гасит повторы
(мигание, остановка на линии).

Один проезд = ровно одно событие. Направление берётся из конфига потока
(топология: камера въезда / камера выезда).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .config import RecognizerConfig
from .pipeline import FrameResult
from .track import SimpleTracker
from .vote import MajorityVote


@dataclass
class _TrackState:
    vote: MajorityVote = field(default_factory=MajorityVote)
    hits: int = 0
    last_frame: object = None  # последний Frame трека
    last_res: FrameResult | None = None
    readings: dict[str, tuple[object, FrameResult]] = field(default_factory=dict)


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
        self.tracker = SimpleTracker()
        self._tracks: dict[int, _TrackState] = {}
        self._cooldown: dict[str, float] = {}

        # наблюдаемость (для /stream/status и /stream/preview)
        self.frames_seen = 0
        self.events_emitted = 0
        self.last_frame: object = None
        self.last_res: FrameResult | None = None
        self.last_plate: str | None = None

    def process(self, frame) -> list[dict]:  # noqa: ANN001
        """Обработать один кадр; вернуть события, эмитнутые на этом кадре."""
        self.frames_seen += 1
        res = self.pipeline.process_frame(frame.image)
        self.last_frame = frame
        self.last_res = res

        if res and res.plate:
            self.last_plate = res.plate
            h, w = frame.image.shape[:2]
            box = res.box or (0, 0, w, h)
            tid = self.tracker.update([box])[0]
            st = self._tracks.setdefault(tid, _TrackState())
            st.vote.add(res.plate, res.confidence)
            st.hits += 1
            st.last_frame = frame
            st.last_res = res
            st.readings[res.plate] = (frame, res)
        else:
            self.tracker.update([])  # старим треки на кадре без номера

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

        frame, res = st.readings[vr.plate]
        voted = replace(res, confidence=vr.confidence)
        rec = self.pipeline._emit(voted, frame, self.sinks)
        if rec:
            self.events_emitted += 1
        return rec
