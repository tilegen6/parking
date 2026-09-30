"""Решение «открыть шлагбаум» по треку машины.

Зачем отдельный модуль. Раньше событие уходило только в момент ЗАКРЫТИЯ трека —
то есть когда машина уже ушла из кадра. Для учёта проездов это нормально (больше
кадров — точнее голосование), но для шлагбаума всегда поздно: водитель стоит,
ничего не происходит, он сдаёт назад — и вот тогда система «просыпается» и
открывает вслед уехавшей машине. Здесь решение принимается на ЖИВОМ кадре, пока
машина ещё перед стрелой.

Модуль намеренно чистый: ни cv2, ни сети, ни ввода-вывода — только числа и время.
Поэтому всю логику ворот можно прогонять в тестах без камеры и без бэкенда.

Состояния трека:

    PENDING ──(все ворота пройдены)──► DECIDED ──(трек закрылся)──► PASSED
       │
       ├──(истёк decide_max_seconds)──► GAVE_UP
       └──(трек закрылся без решения)──► (учётное событие, без открытия)

Инварианты, которые тут держатся:
  * один трек — максимум одно решение «открыть» (`decided`);
  * решение принимается только когда номер виден ПРЯМО СЕЙЧАС (свежесть);
  * машина, которая уменьшается в кадре (уезжает), решения не получает.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

Box = tuple[float, float, float, float]  # x1, y1, x2, y2


# --- Причины отказа. Строкой, а не bool — чтобы оператор в Студии видел, ПОЧЕМУ
# не открылось, а не гадал по пустому экрану.
REASON_OK = "ok"
REASON_ALREADY = "already_decided"
REASON_GAVE_UP = "gave_up"
REASON_STALE = "stale_hit"  # номер давно не видели в кадре
REASON_NO_BOX = "no_box"  # нет геометрии (детектор «весь кадр»)
REASON_FEW_VOTES = "few_votes"
REASON_NO_AGREEMENT = "no_agreement"  # чтения не сходятся между собой
REASON_LOW_CONF = "low_confidence"
REASON_BAD_FORMAT = "bad_format"  # не похоже на номер KZ
REASON_TOO_SMALL = "box_too_small"  # машина ещё далеко
REASON_TOO_BIG = "box_too_big"  # почти наверняка не номер
REASON_OUT_OF_ROI = "out_of_roi"  # не в зоне у шлагбаума
REASON_NEVER_GREW = "never_grew"  # объект не приближался (плакат, фон)
REASON_LEAVING = "leaving"  # машина уменьшается — уезжает


@dataclass
class GateParams:
    """Пороги принятия решения. Значения по умолчанию — консервативные."""

    freshness_seconds: float = 0.7  # номер должен быть виден «сейчас»
    min_votes: int = 3  # минимум чтений победившего номера
    agree_ratio: float = 0.6  # доля голосов за победителя
    vote_margin: int = 2  # отрыв от второго кандидата
    confidence: float = 0.85  # порог уверенности (совпадает с backend)
    require_valid_format: bool = True  # номер должен пройти формат KZ
    max_seconds: float = 20.0  # сколько ждём, прежде чем сдаться
    # геометрия
    min_height_ratio: float = 0.0  # высота номера / высота кадра (0 = не проверять)
    max_height_ratio: float = 0.6
    growth_ratio: float = 1.15  # во сколько раз должен вырасти, чтобы «приближался»
    leave_shrink_ratio: float = 0.8  # доля от максимума, ниже которой считаем «уезжает»
    require_growth: bool = True
    roi: Box | None = None  # зона у шлагбаума в долях кадра (x1,y1,x2,y2)


@dataclass
class TrackGate:
    """Состояние одного трека с точки зрения решения о шлагбауме."""

    started_at: float
    last_hit: float = 0.0
    decided: bool = False
    decided_plate: str | None = None
    gave_up: bool = False
    last_box: Box | None = None
    first_area: float | None = None
    area_max: float = 0.0
    # Короткая история площадей — по ней видно, что машина уменьшается (уезжает).
    area_hist: deque[float] = field(default_factory=lambda: deque(maxlen=4))
    ever_grew: bool = False
    last_reason: str = REASON_FEW_VOTES

    def observe(self, box: Box | None, now: float) -> None:
        """Зафиксировать попадание трека на кадре."""
        self.last_hit = now
        if box is None:
            return
        self.last_box = box
        area = max(0.0, (box[2] - box[0])) * max(0.0, (box[3] - box[1]))
        if area <= 0:
            return
        if self.first_area is None:
            self.first_area = area
        self.area_max = max(self.area_max, area)
        self.area_hist.append(area)
        if self.first_area and area >= self.first_area * 1.15:
            # «Хоть раз приблизился» — взводится один раз и больше не гаснет:
            # машина, подъехавшая и вставшая у стрелы, расти перестаёт, и
            # требовать роста на каждом кадре означало бы её не пустить.
            self.ever_grew = True


def _in_roi(box: Box, roi: Box, frame_w: float, frame_h: float) -> bool:
    """Якорь бокса — нижняя середина (ближняя к полотну точка номера).

    Берём именно её, а не центр: у машины на соседней полосе бокс может краем
    залезть в зону, но его нижняя середина останется снаружи.
    """
    if frame_w <= 0 or frame_h <= 0:
        return False
    ax = ((box[0] + box[2]) / 2) / frame_w
    ay = box[3] / frame_h
    return roi[0] <= ax <= roi[2] and roi[1] <= ay <= roi[3]


def evaluate(
    gate: TrackGate,
    vote,  # VoteResult | None
    now: float,
    params: GateParams,
    frame_size: tuple[int, int],
    is_valid_format: bool = True,
) -> str:
    """Можно ли открыть шлагбаум этому треку прямо сейчас.

    Возвращает REASON_OK либо причину отказа. Порядок проверок — от дешёвых к
    дорогим, чтобы в статистике причина была самой «ранней» и понятной.
    """
    if gate.decided:
        return REASON_ALREADY
    if gate.gave_up:
        return REASON_GAVE_UP

    # Свежесть — главный предохранитель против «открыли вслед уехавшей».
    if now - gate.last_hit > params.freshness_seconds:
        return REASON_STALE

    if vote is None or not vote.plate:
        return REASON_FEW_VOTES

    # Без геометрии нельзя проверить ни зону, ни приближение → не открываем.
    # Это осознанный fail-closed: детектор «весь кадр» (whole) боксов не даёт.
    if gate.last_box is None:
        return REASON_NO_BOX

    if vote.votes < params.min_votes:
        return REASON_FEW_VOTES

    ratio = vote.votes / vote.total if vote.total else 0.0
    if ratio < params.agree_ratio or (vote.votes - vote.runner_up) < params.vote_margin:
        return REASON_NO_AGREEMENT

    if vote.confidence < params.confidence:
        return REASON_LOW_CONF
    if params.require_valid_format and not is_valid_format:
        return REASON_BAD_FORMAT

    frame_h, frame_w = frame_size[0], frame_size[1]
    box = gate.last_box
    if params.min_height_ratio > 0 or params.max_height_ratio < 1.0:
        h_ratio = (box[3] - box[1]) / frame_h if frame_h else 0.0
        if h_ratio < params.min_height_ratio:
            return REASON_TOO_SMALL
        if h_ratio > params.max_height_ratio:
            return REASON_TOO_BIG

    if params.roi is not None and not _in_roi(box, params.roi, frame_w, frame_h):
        return REASON_OUT_OF_ROI

    # Статичный объект (номер на плакате, припаркованная в фоне машина) голосует
    # идеально и бесконечно — по одним голосам его бы пустили. Требуем, чтобы
    # объект хоть раз реально приблизился.
    if params.require_growth and not gate.ever_grew:
        return REASON_NEVER_GREW

    # Сравниваем с МАКСИМУМОМ, а не с первым кадром: трек, начавшийся далеко,
    # уже на отъезде может дать «вырос относительно первого» и проскочить.
    if gate.area_hist and gate.area_max > 0:
        if gate.area_hist[-1] < params.leave_shrink_ratio * gate.area_max:
            return REASON_LEAVING

    return REASON_OK
