"""Метрики оценки распознавания: точное совпадение и посимвольная точность."""

from __future__ import annotations

import re

_ALNUM = re.compile(r"[^A-Z0-9]")


def normalize_for_compare(s: str) -> str:
    """Привести к сравнимому виду: верхний регистр, только буквы/цифры."""
    return _ALNUM.sub("", (s or "").upper())


def levenshtein(a: str, b: str) -> int:
    """Редакционное расстояние (вставка/удаление/замена)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def char_accuracy(pred: str, gt: str) -> float:
    """Доля совпавших символов = 1 - расстояние/длина (0..1)."""
    p, g = normalize_for_compare(pred), normalize_for_compare(gt)
    if not g:
        return 1.0 if not p else 0.0
    return max(0.0, 1.0 - levenshtein(p, g) / max(len(p), len(g)))


def is_exact(pred: str, gt: str) -> bool:
    """Точное совпадение номера (после нормализации)."""
    g = normalize_for_compare(gt)
    return bool(g) and normalize_for_compare(pred) == g
