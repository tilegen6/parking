"""Тесты метрик оценки."""

from recognizer.metrics import (
    char_accuracy,
    is_exact,
    levenshtein,
    normalize_for_compare,
)


def test_levenshtein():
    assert levenshtein("ABC", "ABC") == 0
    assert levenshtein("ABC", "ABD") == 1
    assert levenshtein("", "ABC") == 3
    assert levenshtein("ABC", "") == 3


def test_normalize_for_compare():
    assert normalize_for_compare("127 ast-02") == "127AST02"
    assert normalize_for_compare("") == ""


def test_is_exact():
    assert is_exact("127AST02", "127 AST 02")  # пробелы/регистр игнорируются
    assert not is_exact("127AST01", "127AST02")
    assert not is_exact("", "ABC")  # пусто != номер


def test_char_accuracy():
    assert char_accuracy("127AST02", "127AST02") == 1.0
    assert char_accuracy("127AST01", "127AST02") == 7 / 8  # 1 из 8 символов
    assert char_accuracy("", "ABC") == 0.0
    assert char_accuracy("XYZ", "ABC") == 0.0
