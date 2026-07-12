"""Нормализация и валидация номерных знаков (форматы Казахстана), ТЗ 2.3.

Нормализация **позиционная**: в позициях-цифрах буквы приводятся к цифрам, в
позициях-буквах цифры приводятся к буквам — согласно формату. Это надёжнее
глобальной замены, которая ломала бы валидные буквы (например `B`/`S` в `A123BCD`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Буква, которую OCR выдал вместо цифры -> правильная цифра (таблица из ТЗ)
LETTER_TO_DIGIT = {"O": "0", "I": "1", "B": "8", "S": "5", "Z": "2", "G": "6"}
# Обратное направление: цифра, прочитанная вместо буквы -> буква
DIGIT_TO_LETTER = {v: k for k, v in LETTER_TO_DIGIT.items()}

# Форматы KZ: D = цифра, L = буква
KZ_FORMATS = {
    "NNNLLLNN": "DDDLLLDD",  # 123ABC01, 777AAA02
    "LNNNLLL": "LDDDLLL",  # A123BCD
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


@dataclass(frozen=True)
class PlateNormalization:
    raw: str
    normalized: str
    is_valid: bool
    plate_format: str | None


def _coerce(ch: str, want_digit: bool) -> str:
    """Привести символ к ожидаемому классу через карту путаемых символов."""
    if want_digit:
        return LETTER_TO_DIGIT.get(ch, ch)
    return DIGIT_TO_LETTER.get(ch, ch)


def _matches_class(ch: str, want_digit: bool) -> bool:
    return ch.isdigit() if want_digit else ch.isalpha()


def normalize_plate(raw: str) -> PlateNormalization:
    """Очистить, привести к верхнему регистру, попытаться уложить в формат KZ."""
    cleaned = _NON_ALNUM.sub("", (raw or "").upper())
    for name, pattern in KZ_FORMATS.items():
        if len(cleaned) != len(pattern):
            continue
        coerced = "".join(
            _coerce(ch, want_digit=(cls == "D")) for ch, cls in zip(cleaned, pattern)
        )
        if all(_matches_class(ch, cls == "D") for ch, cls in zip(coerced, pattern)):
            return PlateNormalization(raw, coerced, True, name)
    return PlateNormalization(raw, cleaned, False, None)


def validate_kz(plate: str) -> bool:
    """Проходит ли (нормализованный) номер один из форматов KZ."""
    return normalize_plate(plate).is_valid
