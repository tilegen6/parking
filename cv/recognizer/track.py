"""Простой трекер объектов (ТЗ 2.5): один объект = один трек.

IoU-ассоциация боксов между кадрами. Новый трек — если бокс не пересекается с
активными достаточно сильно. Трек «истекает» после max_age кадров без апдейта.
Это лёгкая замена ByteTrack/DeepSORT для MVP, за тем же интерфейсом.
"""

from __future__ import annotations

from dataclasses import dataclass

Box = tuple[float, float, float, float]  # x1, y1, x2, y2


def iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    box: Box
    age: int = 0  # кадров с последнего апдейта
    hits: int = 0


class SimpleTracker:
    def __init__(self, iou_threshold: float = 0.3, max_age: int = 5) -> None:
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self._tracks: list[Track] = []
        self._next_id = 1

    @property
    def active(self) -> list[Track]:
        return list(self._tracks)

    def update(self, boxes: list[Box]) -> list[int]:
        """Сопоставить боксы кадра с треками; вернуть track_id для каждого бокса."""
        for t in self._tracks:
            t.age += 1

        assigned: list[int] = []
        used: set[int] = set()
        for box in boxes:
            best_t: Track | None = None
            best_iou = self.iou_threshold
            for t in self._tracks:
                if id(t) in used:
                    continue
                v = iou(t.box, box)
                if v >= best_iou:
                    best_t, best_iou = t, v
            if best_t is None:
                best_t = Track(self._next_id, box)
                self._next_id += 1
                self._tracks.append(best_t)
            else:
                best_t.box = box
            best_t.age = 0
            best_t.hits += 1
            used.add(id(best_t))
            assigned.append(best_t.track_id)

        self._tracks = [t for t in self._tracks if t.age <= self.max_age]
        return assigned
