"""Ворота решения «открыть шлагбаум».

Модуль gate.py чистый (без cv2/сети), поэтому здесь проверяется вся логика
принятия решения: и то, что машину пускают, и — что важнее — все случаи, когда
пускать нельзя.
"""

from __future__ import annotations

from recognizer import gate as gate_mod
from recognizer.vote import VoteResult

FRAME = (480, 640)  # h, w


def _vote(plate="777ABC01", votes=5, total=5, conf=0.95, runner_up=0) -> VoteResult:
    return VoteResult(
        plate=plate,
        confidence=conf,
        votes=votes,
        total=total,
        score=conf * votes,
        runner_up=runner_up,
    )


def _approaching(now: float = 10.0) -> gate_mod.TrackGate:
    """Трек машины, которая подъехала: площадь росла, номер виден только что."""
    g = gate_mod.TrackGate(started_at=now - 2.0)
    for i, size in enumerate((40, 60, 90, 120)):
        box = (100.0, 100.0, 100.0 + size * 3, 100.0 + size)
        g.observe(box, now - 1.5 + i * 0.4)
    g.last_hit = now
    return g


def _params(**over) -> gate_mod.GateParams:
    base: dict = {"min_height_ratio": 0.0, "roi": None}
    base.update(over)
    return gate_mod.GateParams(**base)


def test_approaching_car_is_allowed():
    g = _approaching()
    assert gate_mod.evaluate(g, _vote(), 10.0, _params(), FRAME) == gate_mod.REASON_OK


def test_stale_hit_blocks_open():
    """Главный предохранитель: номер не виден «сейчас» — не открываем.

    Именно этот случай раньше давал «машина уехала, а шлагбаум открылся».
    """
    g = _approaching(now=10.0)
    later = 10.0 + 2.0  # номер не появлялся 2 секунды
    assert (
        gate_mod.evaluate(g, _vote(), later, _params(), FRAME) == gate_mod.REASON_STALE
    )


def test_decided_track_does_not_open_twice():
    g = _approaching()
    g.decided = True
    assert (
        gate_mod.evaluate(g, _vote(), 10.0, _params(), FRAME) == gate_mod.REASON_ALREADY
    )


def test_few_votes_blocks():
    g = _approaching()
    assert (
        gate_mod.evaluate(g, _vote(votes=2, total=2), 10.0, _params(), FRAME)
        == gate_mod.REASON_FEW_VOTES
    )


def test_flicker_between_two_plates_blocks():
    """Мигание A/B/A/B: доля высокая, но отрыва нет — не открываем."""
    g = _approaching()
    v = _vote(votes=3, total=6, runner_up=3)
    assert (
        gate_mod.evaluate(g, v, 10.0, _params(), FRAME) == gate_mod.REASON_NO_AGREEMENT
    )


def test_low_confidence_blocks():
    g = _approaching()
    assert (
        gate_mod.evaluate(g, _vote(conf=0.6), 10.0, _params(), FRAME)
        == gate_mod.REASON_LOW_CONF
    )


def test_bad_format_blocks_when_required():
    g = _approaching()
    r = gate_mod.evaluate(g, _vote(), 10.0, _params(), FRAME, is_valid_format=False)
    assert r == gate_mod.REASON_BAD_FORMAT


def test_no_box_fails_closed():
    """Детектор «весь кадр» боксов не даёт — геометрию проверить нечем."""
    g = gate_mod.TrackGate(started_at=9.0, last_hit=10.0)
    assert (
        gate_mod.evaluate(g, _vote(), 10.0, _params(), FRAME) == gate_mod.REASON_NO_BOX
    )


def test_static_object_never_opens():
    """Номер на плакате / припаркованная в фоне: голосует идеально, но не растёт."""
    g = gate_mod.TrackGate(started_at=8.0)
    for i in range(6):
        g.observe((100.0, 100.0, 220.0, 140.0), 8.0 + i * 0.2)  # площадь постоянна
    g.last_hit = 10.0
    assert (
        gate_mod.evaluate(g, _vote(), 10.0, _params(), FRAME)
        == gate_mod.REASON_NEVER_GREW
    )


def test_leaving_car_blocked_even_if_it_grew_before():
    """Машина уезжает: сравниваем с максимумом, а не с первым кадром."""
    g = _approaching()
    # площадь резко упала относительно максимума
    g.observe((100.0, 100.0, 140.0, 115.0), 10.0)
    g.last_hit = 10.0
    assert (
        gate_mod.evaluate(g, _vote(), 10.0, _params(), FRAME) == gate_mod.REASON_LEAVING
    )


def test_far_car_blocked_by_min_height():
    g = gate_mod.TrackGate(started_at=8.0)
    for i, size in enumerate((5, 7, 9, 11)):  # растёт, но всё ещё мелкий
        g.observe((10.0, 10.0, 10.0 + size * 3, 10.0 + size), 8.0 + i * 0.3)
    g.last_hit = 10.0
    p = _params(min_height_ratio=0.05)  # номер должен занимать ≥5% высоты кадра
    assert gate_mod.evaluate(g, _vote(), 10.0, p, FRAME) == gate_mod.REASON_TOO_SMALL


def test_roi_blocks_neighbour_lane():
    """Машина по соседней полосе: бокс краем в зоне, но якорь — снаружи."""
    g = gate_mod.TrackGate(started_at=8.0)
    for i, size in enumerate((40, 60, 90, 120)):
        # far left of the frame
        g.observe((0.0, 100.0, 0.0 + size * 3, 100.0 + size), 8.0 + i * 0.3)
    g.last_hit = 10.0
    p = _params(roi=(0.5, 0.0, 1.0, 1.0))  # зона — правая половина кадра
    assert gate_mod.evaluate(g, _vote(), 10.0, p, FRAME) == gate_mod.REASON_OUT_OF_ROI


def test_roi_allows_car_in_zone():
    g = _approaching()  # бокс в районе x≈100..460 из 640 → якорь ~0.43
    p = _params(roi=(0.0, 0.0, 0.9, 1.0))
    assert gate_mod.evaluate(g, _vote(), 10.0, p, FRAME) == gate_mod.REASON_OK


def test_gave_up_track_stays_closed():
    g = _approaching()
    g.gave_up = True
    assert (
        gate_mod.evaluate(g, _vote(), 10.0, _params(), FRAME) == gate_mod.REASON_GAVE_UP
    )
