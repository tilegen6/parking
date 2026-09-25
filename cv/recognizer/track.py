"""Простой трекер объектов (ТЗ 2.5): один объект = один трек.

IoU-ассоциация боксов между кадрами. Новый трек — если бокс не пересекается с
активными достаточно сильно. Это лёгкая замена ByteTrack/DeepSORT для MVP, за
тем же интерфейсом.

Трек истекает по ВРЕМЕНИ (max_age_seconds), если в `update` передан `now`. Счёт
в кадрах врёт на живом потоке: шаг кадра плавает от инференса и реконнектов
(`sources.py` спит `1/fps`, но при отсутствии свежего кадра пропускает такт), и
«5 кадров» — это то 1 секунда, то 5. Без `now` работает старый счёт по кадрам —
для батч-обработки файлов, где время кадра не имеет смысла.

Трек, потерявший бокс, переподхватывается по МЯГКОМУ порогу IoU: за время паузы
машина уезжает из своего прежнего бокса, и строгий порог породил бы дубль-трек.
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
    age: int = 0  # кадров с последнего апдейта (режим без времени)
    hits: int = 0
    last_seen: float = 0.0  # монотонное время последнего попадания (режим времени)


class SimpleTracker:
    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_age: int = 5,
        max_age_seconds: float = 1.5,
        reacquire_iou: float = 0.1,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.max_age_seconds = max_age_seconds
        # Мягкий порог для трека, который уже терял бокс (см. докстринг модуля)
        self.reacquire_iou = reacquire_iou
        self._tracks: list[Track] = []
        self._next_id = 1

    @property
    def active(self) -> list[Track]:
        return list(self._tracks)

    def update(self, boxes: list[Box], now: float | None = None) -> list[int]:
        """Сопоставить боксы кадра с треками; вернуть track_id для каждого бокса.

        `now` — монотонные секунды. Задан → трек истекает по времени; не задан →
        по числу кадров (обратная совместимость для офлайн-обработки).
        """
        for t in self._tracks:
            t.age += 1

        assigned: list[int] = []
        used: set[int] = set()
        for box in boxes:
            best_t: Track | None = None
            best_iou = 0.0
            for t in self._tracks:
                if id(t) in used:
                    continue
                # Трек, потерявший бокс на прошлых кадрах, ищем мягче: за паузу
                # машина успевает сместиться, и строгий порог родил бы дубль.
                threshold = self.reacquire_iou if t.age > 1 else self.iou_threshold
                v = iou(t.box, box)
                if v >= threshold and v > best_iou:
                    best_t, best_iou = t, v
            if best_t is None:
                best_t = Track(self._next_id, box, last_seen=now or 0.0)
                self._next_id += 1
                self._tracks.append(best_t)
            else:
                best_t.box = box
            best_t.age = 0
            best_t.hits += 1
            if now is not None:
                best_t.last_seen = now
            used.add(id(best_t))
            assigned.append(best_t.track_id)

        if now is not None:
            self._tracks = [
                t for t in self._tracks if (now - t.last_seen) <= self.max_age_seconds
            ]
        else:
            self._tracks = [t for t in self._tracks if t.age <= self.max_age]
        return assigned
