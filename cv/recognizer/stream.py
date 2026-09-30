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
from .gate import GateParams, TrackGate
from .gate import evaluate as gate_evaluate
from .normalize import normalize_plate
from .pipeline import FrameResult
from .quality import frame_ok
from .track import SimpleTracker
from .vote import MajorityVote


def _parse_roi(raw: str):  # noqa: ANN202 — tuple[float,float,float,float] | None
    """ROI из строки "x1,y1,x2,y2" в долях кадра. Мусор — как «не задано»."""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(p) for p in parts)
    except ValueError:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def _gate_params_from(cfg: RecognizerConfig) -> GateParams:
    return GateParams(
        freshness_seconds=cfg.gate_freshness_seconds,
        min_votes=cfg.gate_min_votes,
        agree_ratio=cfg.gate_agree_ratio,
        vote_margin=cfg.gate_vote_margin,
        confidence=cfg.gate_confidence,
        require_valid_format=cfg.gate_require_valid_format,
        max_seconds=cfg.gate_max_seconds,
        min_height_ratio=cfg.gate_min_height_ratio,
        max_height_ratio=cfg.gate_max_height_ratio,
        growth_ratio=cfg.gate_growth_ratio,
        leave_shrink_ratio=cfg.gate_leave_shrink_ratio,
        require_growth=cfg.gate_require_growth,
        roi=_parse_roi(cfg.gate_roi),
    )


@dataclass
class _TrackState:
    vote: MajorityVote = field(default_factory=MajorityVote)
    hits: int = 0
    last_frame: object = None  # последний Frame трека
    last_res: FrameResult | None = None
    gate: TrackGate | None = None  # состояние решения о шлагбауме


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
        # Два РАЗНЫХ кулдауна. Общий словарь означал бы, что учётное событие
        # (низкая уверенность, «наблюдение») на минуту глушит легитимный сигнал
        # открытия по тому же номеру.
        self._cooldown: dict[str, float] = {}  # учётные события
        self._decisions: dict[str, float] = {}  # принятые решения «открыть»
        self._gate_params = _gate_params_from(cfg)

        # наблюдаемость (для /stream/status и /stream/preview)
        self.frames_seen = 0
        self.events_emitted = 0
        self.frames_dropped = 0  # отсеяно фильтром качества (смаз/темнота)
        self.opens_emitted = 0  # решений «открыть шлагбаум»
        self.stalled = 0  # треков, по которым так и не решили (нужен оператор)
        self.last_frame: object = None
        self.last_res: FrameResult | None = None
        self.last_plate: str | None = None
        self.last_reason: str = ""  # почему не открыли (для Студии)

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
            if st.gate is None:
                st.gate = TrackGate(started_at=now)
            st.vote.add(res.plate, res.confidence)
            st.hits += 1
            st.last_frame = frame
            st.last_res = res
            st.gate.observe(res.box, now)

        out = self._try_decide(now, (h, w))
        return out + self._collect_closed()

    def _try_decide(self, now: float, frame_size: tuple[int, int]) -> list[dict]:
        """Решение об открытии — на ЖИВОМ кадре, пока машина ещё перед стрелой.

        Ждать закрытия трека нельзя: к тому моменту машина уже ушла из кадра, и
        сигнал уходит вслед уехавшей.
        """
        if not self.cfg.gate_enabled:
            return []
        out: list[dict] = []
        for st in self._tracks.values():
            g = st.gate
            if g is None or g.decided or g.gave_up:
                continue
            vr = st.vote.result()
            is_valid = normalize_plate(vr.plate).is_valid if vr and vr.plate else False
            reason = gate_evaluate(
                g, vr, now, self._gate_params, frame_size, is_valid_format=is_valid
            )
            g.last_reason = reason
            self.last_reason = reason

            if reason == "ok" and vr is not None:
                if self._on_open_cooldown(vr.plate, now):
                    # Тот же номер только что пустили: трек развалился и родился
                    # заново (машина дёрнулась). Второй сигнал не шлём, но и
                    # «не проехал» потом не пишем — считаем решение принятым.
                    g.decided = True
                    g.decided_plate = vr.plate
                    continue
                rec = self._emit_track(st, decision="open", now=now)
                g.decided = True
                g.decided_plate = vr.plate
                if rec:
                    self._decisions[vr.plate] = now
                    self.opens_emitted += 1
                    out.append(rec)
            elif now - g.started_at > self._gate_params.max_seconds:
                # Сдаёмся: номер грязный/нечитаемый. Не крутим проверку вечно и
                # не молчим — оператор должен увидеть и открыть вручную.
                g.gave_up = True
                self.stalled += 1
        self._gc_decisions(now)
        return out

    def _on_open_cooldown(self, plate: str, now: float) -> bool:
        prev = self._decisions.get(plate)
        return prev is not None and (now - prev) < self.cfg.gate_max_seconds

    def _gc_decisions(self, now: float) -> None:
        """Чистим реестр решений: без этого словарь растёт весь срок работы."""
        ttl = self.cfg.gate_max_seconds
        stale = [p for p, t in self._decisions.items() if now - t > ttl]
        for p in stale:
            self._decisions.pop(p, None)

    def _close_track(self, st: _TrackState) -> dict | None:
        """Трек закрылся (машина ушла из кадра).

        Если по нему уже принято решение «открыть» — событие ушло тогда же, и
        второй раз слать нечего: один проезд = один POST. Иначе это учётное
        событие: машина проехала/постояла, а уверенности на открытие не набралось.
        """
        if st.gate is not None and st.gate.decided:
            return None
        return self._emit_track(st, decision="observe")

    def _collect_closed(self) -> list[dict]:
        """Эмитим треки, которые только что выпали из активных (машина уехала)."""
        active = {t.track_id for t in self.tracker.active}
        closed = [tid for tid in self._tracks if tid not in active]
        out = []
        for tid in closed:
            rec = self._close_track(self._tracks.pop(tid))
            if rec:
                out.append(rec)
        return out

    def flush(self) -> list[dict]:
        """Закрыть все открытые треки (вызывать на остановке потока)."""
        out = []
        for tid in list(self._tracks):
            rec = self._close_track(self._tracks.pop(tid))
            if rec:
                out.append(rec)
        return out

    def _emit_track(
        self,
        st: _TrackState,
        decision: str = "observe",
        now: float | None = None,
    ) -> dict | None:
        """Отправить событие по треку.

        `decision="open"` — сигнал шлагбауму (принят на живом кадре);
        `decision="observe"` — учётное событие на закрытии трека.
        """
        if st.hits < self.cfg.min_hits:
            return None
        vr = st.vote.result()
        if not vr or not vr.plate:
            return None

        now = self._clock() if now is None else now
        if decision != "open":
            # Кулдаун учёта не касается решений: иначе наблюдение на минуту
            # заблокировало бы легитимное открытие по тому же номеру.
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
        rec = self._call_emit(voted, st.last_frame, decision)
        if rec:
            self.events_emitted += 1
        return rec

    def _call_emit(self, voted: FrameResult, frame, decision: str):  # noqa: ANN001,ANN202
        """Вызов pipeline._emit с decision, если он его принимает.

        Контракт `pipeline` объявлен в докстринге класса и реализован тестовыми
        дублями — старую сигнатуру без `decision` молча ломать нельзя.
        """
        try:
            return self.pipeline._emit(voted, frame, self.sinks, decision=decision)
        except TypeError:
            return self.pipeline._emit(voted, frame, self.sinks)
