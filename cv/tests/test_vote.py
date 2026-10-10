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


def test_empty_returns_none():
    assert MajorityVote().result() is None


def test_ignores_empty_plates():
    v = MajorityVote()
    v.add("", 0.99)
    assert len(v) == 0
    assert v.result() is None
