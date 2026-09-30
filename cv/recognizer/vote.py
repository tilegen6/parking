"""Majority-vote стабилизация (ТЗ 2.4).

Нельзя создавать событие по одному кадру. Копим (номер, confidence) и выбираем
номер с максимальным СУММАРНЫМ весом уверенности (score), а не по числу кадров.

Почему по сумме, а не по количеству: считая кадры, три мутных чтения «777ABC01»
(по 0.5) побеждали два уверенных «777AVC01» (по 0.95) — количество било качество,
и на выходе оказывался неверный номер. Сумма confidence складывает и то, и другое:
частое чтение выигрывает за счёт числа слагаемых, уверенное — за счёт их величины.
При равной сумме предпочитаем номер, прочитанный большее число раз (стабильность).
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
    # Суммарный вес победителя (sum(confidence)). По нему принимается решение
    # «накопили ли мы достаточно уверенности» — например для открытия шлагбаума,
    # где важно не число кадров, а накопленное качество чтений.
    score: float = 0.0
    # Сколько чтений у ближайшего конкурента. Нужен для «отрыва»: доля голосов
    # не ловит мигание A/B/A/B (там у победителя может быть внушительная доля при
    # нулевом отрыве), а отрыв ловит.
    runner_up: int = 0


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
        # Ключ — суммарная уверенность; при равной сумме больше доверяем номеру,
        # который прочитан большее число раз.
        ranked = sorted(
            self._by_plate.items(),
            key=lambda kv: (sum(kv[1]), len(kv[1])),
            reverse=True,
        )
        plate, confs = ranked[0]
        runner_up = len(ranked[1][1]) if len(ranked) > 1 else 0
        return VoteResult(
            plate=plate,
            # Наружу отдаём СРЕДНЮЮ, а не сумму: это качество чтения, его backend
            # сравнивает с порогом confidence. Сумма живёт отдельно, в score.
            confidence=sum(confs) / len(confs),
            votes=len(confs),
            total=self._total,
            score=sum(confs),
            runner_up=runner_up,
        )
