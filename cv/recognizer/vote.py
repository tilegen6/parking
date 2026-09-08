"""Majority-vote стабилизация (ТЗ 2.4).

Нельзя создавать событие по одному кадру. Копим (номер, confidence) и выбираем
номер с максимальной частотой; при равенстве частот — по средней confidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class VoteResult:
    plate: str
    confidence: float  # средняя confidence для победившего номера
    votes: int  # сколько раз встретился победитель
    total: int  # всего чтений в буфере


class MajorityVote:
    """Буфер чтений одного объекта/трека."""

    def __init__(self) -> None:
        self._by_plate: dict[str, list[float]] = defaultdict(list)
        self._total = 0

    def add(self, plate: str, confidence: float) -> None:
        if plate:
            self._by_plate[plate].append(confidence)
            self._total += 1

    def __len__(self) -> int:
        return self._total

    def result(self) -> VoteResult | None:
        if not self._by_plate:
            return None
        plate, confs = max(
            self._by_plate.items(),
            key=lambda kv: (len(kv[1]), sum(kv[1]) / len(kv[1])),
        )
        return VoteResult(
            plate=plate,
            confidence=sum(confs) / len(confs),
            votes=len(confs),
            total=self._total,
        )
