"""Тесты majority-vote стабилизации."""

from recognizer.vote import MajorityVote


def test_majority_wins():
    v = MajorityVote()
    for p, c in [
        ("777ABC01", 0.9),
        ("777ABC01", 0.92),
        ("777ABC0I", 0.8),
        ("777A8C01", 0.7),
        ("777ABC01", 0.95),
    ]:
        v.add(p, c)
    res = v.result()
    assert res.plate == "777ABC01"
    assert res.votes == 3
    assert res.total == 5


def test_tie_broken_by_confidence():
    v = MajorityVote()
    v.add("AAA", 0.6)
    v.add("AAA", 0.6)
    v.add("BBB", 0.95)
    v.add("BBB", 0.95)
    res = v.result()
    assert res.plate == "BBB"  # та же частота -> выше средняя confidence


def test_quality_beats_quantity():
    """CV-4: два уверенных чтения бьют три мутных.

    Раньше ключом было ЧИСЛО кадров, поэтому серия мутных чтений неверного номера
    побеждала пару уверенных — на выходе получался неправильный номер.
    """
    v = MajorityVote()
    for _ in range(3):
        v.add("777ABC01", 0.5)  # три мутных: сумма 1.5
    for _ in range(2):
        v.add("777AVC01", 0.95)  # два уверенных: сумма 1.9
    res = v.result()
    assert res.plate == "777AVC01"
    assert res.votes == 2
    assert res.confidence == 0.95  # наружу — средняя, а не сумма


def test_frequent_still_wins_when_confidence_close():
    """Частота не обесценена: при близкой уверенности побеждает частое чтение."""
    v = MajorityVote()
    for _ in range(4):
        v.add("777ABC01", 0.80)  # сумма 3.2
    for _ in range(2):
        v.add("777AVC01", 0.90)  # сумма 1.8
    assert v.result().plate == "777ABC01"


def test_score_is_sum_of_confidence():
    """score — накопленный вес победителя (для порога принятия решения)."""
    v = MajorityVote()
    v.add("777ABC01", 0.6)
    v.add("777ABC01", 0.8)
    res = v.result()
    assert res.score == 1.4
    assert res.confidence == 0.7  # средняя


def test_empty_returns_none():
    assert MajorityVote().result() is None


def test_ignores_empty_plates():
    v = MajorityVote()
    v.add("", 0.99)
    assert len(v) == 0
    assert v.result() is None
