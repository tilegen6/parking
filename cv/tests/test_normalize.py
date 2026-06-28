"""Тесты нормализации/валидации номеров (без тяжёлых зависимостей)."""

from recognizer.normalize import normalize_plate, validate_kz


def test_valid_formats():
    assert validate_kz("123ABC01")  # NNNLLLNN
    assert validate_kz("777AAA02")  # NNNLLLNN
    assert validate_kz("A123BCD")  # LNNNLLL


def test_letter_to_digit_in_digit_positions():
    # I->1 в позициях-цифрах; формат DDDLLLDD
    r = normalize_plate("I23ABC0I")
    assert r.is_valid
    assert r.normalized == "123ABC01"
    assert r.plate_format == "NNNLLLNN"


def test_digit_to_letter_in_letter_positions():
    # формат LNNNLLL: последняя позиция — буква, '0' -> 'O'
    r = normalize_plate("A123BC0")
    assert r.is_valid
    assert r.normalized == "A123BCO"
    assert r.plate_format == "LNNNLLL"


def test_does_not_corrupt_valid_letters():
    # B/C/D — валидные буквы в LNNNLLL, не должны превращаться в цифры
    r = normalize_plate("A123BCD")
    assert r.normalized == "A123BCD"


def test_cleans_separators():
    r = normalize_plate("123-abc 01")
    assert r.is_valid
    assert r.normalized == "123ABC01"


def test_invalid_plate():
    r = normalize_plate("HELLO")
    assert not r.is_valid
    assert r.plate_format is None


def test_empty():
    r = normalize_plate("")
    assert not r.is_valid
