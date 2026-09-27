"""Уверенность OCR считается по реальным символам, а не по pad-слотам.

Модель fast-plate-ocr отдаёт вероятности на все max_plate_slots (9), а строка
короче — хвост занят pad-символами, в которых модель почти всегда уверена.
Усреднение по всем слотам завышало оценку, и порог confidence фильтровал вслепую.
"""

from __future__ import annotations

import numpy as np

from recognizer.ocr import _char_confidence


def test_pad_slots_do_not_inflate_confidence():
    """Хвост pad-слотов не должен вытягивать среднее вверх."""
    # 8 реальных символов, один из них слабый; ещё 1 слот — pad с 0.99
    probs = np.array([0.98, 0.35, 0.97, 0.99, 0.98, 0.96, 0.97, 0.98, 0.99])
    mean, low = _char_confidence(probs, "777ABC01")  # 8 символов
    # среднее по 8 реальным, pad-слот не участвует
    assert abs(mean - float(np.mean(probs[:8]))) < 1e-9
    assert low == 0.35  # слабый символ виден честно


def test_min_exposes_single_bad_char():
    """Средняя маскирует одиночную ошибку, минимум — нет."""
    probs = np.array([0.98] * 7 + [0.30])
    mean, low = _char_confidence(probs, "777ABC01")
    assert mean > 0.88  # по средней чтение выглядит хорошим
    assert low == 0.30  # а по минимуму — сомнительным


def test_empty_probs_safe():
    assert _char_confidence(None, "777ABC01") == (0.0, None)
    assert _char_confidence(np.array([]), "777ABC01") == (0.0, None)


def test_text_longer_than_probs_does_not_crash():
    """Строка длиннее вектора вероятностей — берём что есть, без падения."""
    probs = np.array([0.9, 0.8])
    mean, low = _char_confidence(probs, "777ABC01")
    assert abs(mean - 0.85) < 1e-9
    assert low == 0.8
