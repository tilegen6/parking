"""Тесты простого IoU-трекера."""

from recognizer.track import SimpleTracker, iou


def test_iou_basic():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_same_object_keeps_track_id():
    t = SimpleTracker(iou_threshold=0.3)
    id1 = t.update([(0, 0, 10, 10)])[0]
    id2 = t.update([(1, 1, 11, 11)])[0]  # сильно пересекается
    assert id1 == id2


def test_new_object_new_track():
    t = SimpleTracker(iou_threshold=0.3)
    id1 = t.update([(0, 0, 10, 10)])[0]
    id2 = t.update([(100, 100, 110, 110)])[0]  # не пересекается
    assert id1 != id2


def test_two_boxes_two_tracks():
    t = SimpleTracker()
    ids = t.update([(0, 0, 10, 10), (100, 100, 110, 110)])
    assert len(set(ids)) == 2


def test_track_expires_after_max_age():
    t = SimpleTracker(iou_threshold=0.3, max_age=2)
    first = t.update([(0, 0, 10, 10)])[0]
    for _ in range(3):  # кадры без этого объекта -> трек протухает
        t.update([])
    again = t.update([(0, 0, 10, 10)])[0]
    assert again != first
