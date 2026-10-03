"""Тесты Session Service — основные сценарии ТЗ (TC-1…TC-6 + аномалии)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.models import (
    Camera,
    Direction,
    EventFlag,
    Gate,
    ParkingSession,
    RecognitionEvent,
    SessionStatus,
    Tariff,
)
from src.modules import session as svc

T0 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


def _naive(dt: datetime) -> datetime:
    """SQLite отдаёт naive UTC — сравниваем даты без tzinfo."""
    return dt.replace(tzinfo=None)


async def _emit(db, plate, direction, t, conf=0.95, cam=None):
    event = RecognitionEvent(
        plate_number=plate,
        direction=direction,
        event_time=t,
        confidence=conf,
        camera_id=cam,
    )
    db.add(event)
    await db.flush()
    result = await svc.handle_recognition_event(db, event)
    return event, result


async def test_entry_creates_active_session(db):
    _, r = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    assert r.action == "created"
    sess = await db.get(ParkingSession, r.session_id)
    assert sess.status == SessionStatus.ACTIVE
    assert sess.exit_time is None


async def test_active_session_unique_constraint(db):
    """P0-7: БД не даёт двум активным сессиям по одному (номер, шлагбаум).

    Это последняя линия обороны против гонки: даже если два параллельных ENTRY
    оба прошли проверку «активной нет», второй INSERT отвергается.
    """
    from sqlalchemy.exc import IntegrityError

    db.add(
        ParkingSession(
            plate_number="777RACE01",
            status=SessionStatus.ACTIVE,
            entry_time=T0,
        )
    )
    await db.flush()
    db.add(
        ParkingSession(
            plate_number="777RACE01",
            status=SessionStatus.ACTIVE,
            entry_time=T0 + timedelta(seconds=1),
        )
    )
    try:
        await db.flush()
        raise AssertionError("ожидали IntegrityError на второй активной сессии")
    except IntegrityError:
        pass
    await db.rollback()


async def test_closed_session_allows_new_active(db):
    """Уникальность только среди активных: после выезда тот же номер въезжает."""
    db.add(
        ParkingSession(
            plate_number="777RACE02",
            status=SessionStatus.PAID,  # закрыта — вне частичного индекса
            entry_time=T0,
            exit_time=T0 + timedelta(hours=1),
        )
    )
    await db.flush()
    db.add(
        ParkingSession(
            plate_number="777RACE02",
            status=SessionStatus.ACTIVE,
            entry_time=T0 + timedelta(hours=2),
        )
    )
    await db.flush()  # не должно падать


async def test_duplicate_entry_restarts_session_start(db):
    """Машина стоит перед шлагбаумом: старт = ПОСЛЕДНЕЕ событие серии + пометка."""
    e1, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    t2 = T0 + timedelta(seconds=5)
    e2, r2 = await _emit(db, "123ABC02", Direction.ENTRY, t2)
    assert r2.action == "entry_restarted"
    assert r2.session_id == r1.session_id
    assert e2.flag == EventFlag.DUPLICATE  # ТС-2: событие помечено как дубль
    sess = await db.get(ParkingSession, r1.session_id)
    assert _naive(sess.entry_time) == _naive(t2)  # старт сдвинут на последнее
    assert sess.entry_adjusted is True  # пометка для разборов
    assert sess.entry_event_id == e2.id
    total = (
        await db.execute(select(func.count()).select_from(ParkingSession))
    ).scalar_one()
    assert total == 1


async def test_duplicate_entry_outside_window_keeps_start(db):
    """Повторное распознавание стоящей машины (вне окна сдвига) не обнуляет счёт."""
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    # > entry_restart_window (10 мин), но < порога ТС-3 (1 час)
    mid = T0 + timedelta(minutes=30)
    e2, r2 = await _emit(db, "123ABC02", Direction.ENTRY, mid)
    assert r2.action == "updated_last_seen"
    assert e2.flag == EventFlag.DUPLICATE  # ТС-2: событие помечено как дубль
    sess = await db.get(ParkingSession, r1.session_id)
    assert _naive(sess.entry_time) == _naive(T0)  # старт НЕ сдвинут
    assert sess.entry_adjusted is False
    assert _naive(sess.last_seen) == _naive(mid)


async def test_duplicate_entry_series_billed_from_last(db):
    """Счёт идёт от последнего дубля: 10 мин у шлагбаума не тарифицируются."""
    db.add(
        Tariff(
            name="Тест",
            free_minutes=0,
            price_per_hour=200,
            daily_cap=None,
            currency="KZT",
            is_active=True,
        )
    )
    await db.flush()
    await _emit(db, "123ABC02", Direction.ENTRY, T0)
    # серия дублей: машина стоит перед шлагбаумом 10 минут
    for m in (3, 6, 10):
        _, r = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(minutes=m))
        assert r.action == "entry_restarted"
    # выезд через 1 час ПОСЛЕ последнего дубля: без сдвига было бы 70 мин ->
    # ceil 2 часа -> 400; со сдвигом ровно 1 час -> 200 (долг, шлагбаум закрыт)
    _, rx = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=70))
    assert rx.action == "exit_denied_unpaid"
    assert rx.detail == "due=200"
    sess = await db.get(ParkingSession, rx.session_id)
    assert sess.duration_seconds == 3600
    assert sess.price == 200.0


async def test_start_shift_bounded_by_anchor(db):
    """P0-5: сдвиг старта ограничен окном ОТ ЯКОРЯ, а не бесконечно.

    Раньше окно считалось от last_seen: машину, которую камера видит раз в
    9 минут, можно было двигать вечно → безлимитная бесплатная парковка.
    """
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    # +9 мин — внутри окна (10 мин) от якоря T0 → сдвиг
    _, r2 = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(minutes=9))
    assert r2.action == "entry_restarted"
    # +18 мин — 18 > 10 мин ОТ ЯКОРЯ (хотя всего 9 мин от прошлого) → НЕ сдвигаем
    _, r3 = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(minutes=18))
    assert r3.action == "updated_last_seen"
    # +27 мин — тем более не сдвигаем
    _, r4 = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(minutes=27))
    assert r4.action == "updated_last_seen"
    sess = await db.get(ParkingSession, r1.session_id)
    # старт застыл на последнем сдвиге в пределах окна (+9 мин), не уполз дальше
    assert _naive(sess.entry_time) == _naive(T0 + timedelta(minutes=9))


async def test_no_start_shift_after_denied_exit(db):
    """P0-5/#21: после отказа в выезде (долг) повторный ENTRY не обнуляет счёт."""
    db.add(
        Tariff(
            name="Тест",
            free_minutes=0,
            price_per_hour=200,
            daily_cap=None,
            currency="KZT",
            is_active=True,
        )
    )
    await db.flush()
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    # выезд через час — недоплата, шлагбаум закрыт, сессия осталась активной
    _, rx = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=1))
    assert rx.action == "exit_denied_unpaid"
    # водитель подъезжает к въездной камере ещё раз (объехал/развернулся)
    _, r2 = await _emit(
        db, "123ABC02", Direction.ENTRY, T0 + timedelta(hours=1, seconds=30)
    )
    # старт НЕ сдвигается — долг не должен обнуляться
    assert r2.action == "updated_last_seen"
    sess = await db.get(ParkingSession, r1.session_id)
    assert _naive(sess.entry_time) == _naive(T0)
    assert sess.price == 200.0  # накопленный долг цел


async def test_entry_exit_closes_when_free(db):
    # без активного тарифа парковка бесплатна -> шлагбаум открыт -> paid
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    _, r3 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30))
    assert r3.action == "closed"
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.status == SessionStatus.PAID
    assert sess.duration_seconds == 1800


async def test_duplicate_exit_ignored(db):
    await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30))
    _, r = await _emit(
        db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30, seconds=3)
    )
    assert r.action == "duplicate_exit"


async def test_exit_without_session_flags_event(db):
    event, r = await _emit(db, "999ZZZ09", Direction.EXIT, T0)
    assert r.action == "event_without_session"
    assert event.flag == EventFlag.EVENT_WITHOUT_SESSION
    total = (
        await db.execute(select(func.count()).select_from(ParkingSession))
    ).scalar_one()
    assert total == 0


async def test_low_confidence_skips_session(db):
    event, r = await _emit(db, "777BBB07", Direction.ENTRY, T0, conf=0.5)
    assert r.action == "low_confidence"
    assert event.flag == EventFlag.LOW_CONFIDENCE


async def test_null_plate_is_low_confidence(db):
    _, r = await _emit(db, None, Direction.ENTRY, T0, conf=0.99)
    assert r.action == "low_confidence"


async def test_reentry_after_exit_creates_new_session(db):
    # выезд закрыл сессию -> следующий въезд = новая активная
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30))
    _, r2 = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(hours=2))
    assert r2.action == "created"
    assert r2.session_id != r1.session_id


async def test_exit_denied_when_unpaid(db):
    # активный тариф 100/час; выезд без оплаты -> шлагбаум закрыт, сессия активна
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=100, daily_cap=None, is_active=True
        )
    )
    await db.flush()
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    _, r3 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    assert r3.action == "exit_denied_unpaid"
    assert r3.detail == "due=200"
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.status == SessionStatus.ACTIVE  # остался на парковке
    assert sess.exit_time is None
    assert sess.price == 200  # долг для отображения


async def test_exit_without_tariff_leaves_price_none(db):
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.price is None
    assert sess.status == SessionStatus.PAID  # бесплатно -> выпущен


# ── ТС-3: повторный въезд без выезда через большой промежуток ──────────────


async def test_reentry_after_gap_closes_old_creates_new(db):
    """Пропущенный выезд: старую сессию -> auto_closed, новую открыть."""
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    _, r2 = await _emit(db, "123ABC02", Direction.ENTRY, T0 + timedelta(hours=2))
    assert r2.action == "reentry_new_session"
    assert r2.session_id != r1.session_id
    old = await db.get(ParkingSession, r1.session_id)
    new = await db.get(ParkingSession, r2.session_id)
    assert old.status == SessionStatus.AUTO_CLOSED
    assert old.exit_time is None  # реальный момент выезда неизвестен
    assert new.status == SessionStatus.ACTIVE
    assert _naive(new.entry_time) == _naive(T0 + timedelta(hours=2))


# ── ТС-7: направление UNKNOWN ───────────────────────────────────────────────


async def test_unknown_direction_flags_event_no_session(db):
    event, r = await _emit(db, "123ABC02", Direction.UNKNOWN, T0)
    assert r.action == "ignored"
    assert event.flag == EventFlag.UNKNOWN_DIRECTION
    total = (
        await db.execute(select(func.count()).select_from(ParkingSession))
    ).scalar_one()
    assert total == 0


# ── ТС-9: похожий номер (±1 символ) — possible_misread ─────────────────────


async def test_entry_similar_plate_flagged_not_created(db):
    """O↔0/1 символ разницы с активной сессией: не создаём, на проверку."""
    await _emit(db, "123ABC02", Direction.ENTRY, T0)
    event, r = await _emit(db, "123ABC0Z", Direction.ENTRY, T0 + timedelta(minutes=5))
    assert r.action == "possible_misread"
    assert event.flag == EventFlag.POSSIBLE_MISREAD
    total = (
        await db.execute(select(func.count()).select_from(ParkingSession))
    ).scalar_one()
    assert total == 1  # вторая сессия НЕ создана


async def test_exit_similar_plate_flagged_session_untouched(db):
    """EXIT похожего номера не закрывает чужую сессию — на ручную проверку."""
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    event, r = await _emit(db, "123ABC0Z", Direction.EXIT, T0 + timedelta(minutes=30))
    assert r.action == "possible_misread"
    assert event.flag == EventFlag.POSSIBLE_MISREAD
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.status == SessionStatus.ACTIVE
    assert sess.exit_time is None


async def test_two_char_difference_creates_normally(db):
    """Разница в 2+ символа — реально другая машина, сессия создаётся."""
    await _emit(db, "123ABC02", Direction.ENTRY, T0)
    _, r = await _emit(db, "123ABD03", Direction.ENTRY, T0 + timedelta(minutes=5))
    assert r.action == "created"


# ── ТС-2: дубль выезда тоже помечается ──────────────────────────────────────


async def test_duplicate_exit_flags_event(db):
    await _emit(db, "123ABC02", Direction.ENTRY, T0)
    await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30))
    event, r = await _emit(
        db, "123ABC02", Direction.EXIT, T0 + timedelta(minutes=30, seconds=3)
    )
    assert r.action == "duplicate_exit"
    assert event.flag == EventFlag.DUPLICATE


# ── Итерация 1: раздельный учёт по шлагбаумам ───────────────────────────────


async def _gate_cam(db, gate_name, zone, level, cam_name):
    gate = Gate(name=gate_name, zone=zone, level=level)
    db.add(gate)
    await db.flush()
    cam = Camera(name=cam_name, gate_id=gate.id)
    db.add(cam)
    await db.flush()
    return gate, cam


async def test_same_plate_two_gates_two_sessions(db):
    """Один номер на двух шлагбаумах = две независимые сессии (двор + отель)."""
    g1, c1 = await _gate_cam(db, "КПП двор", "Двор", 1, "cam-yard")
    g2, c2 = await _gate_cam(db, "Отель", "Отель", 2, "cam-hotel")

    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0, cam=c1.id)
    _, r2 = await _emit(
        db, "123ABC02", Direction.ENTRY, T0 + timedelta(minutes=1), cam=c2.id
    )
    assert r1.action == "created"
    assert r2.action == "created"  # другой шлагбаум -> отдельная сессия
    assert r1.session_id != r2.session_id

    s1 = await db.get(ParkingSession, r1.session_id)
    s2 = await db.get(ParkingSession, r2.session_id)
    assert s1.gate_id == g1.id
    assert s2.gate_id == g2.id

    active = (
        await db.execute(
            select(func.count())
            .select_from(ParkingSession)
            .where(ParkingSession.status == SessionStatus.ACTIVE)
        )
    ).scalar_one()
    assert active == 2

    # выезд на дворовом шлагбауме закрывает только дворовую сессию
    _, rx = await _emit(
        db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=1), cam=c1.id
    )
    assert rx.action == "closed"
    assert rx.session_id == r1.session_id
    hotel = await db.get(ParkingSession, r2.session_id)
    assert hotel.status == SessionStatus.ACTIVE  # отель ещё занят


async def test_reentry_same_gate_is_duplicate(db):
    """Повторный въезд на ТОТ ЖЕ шлагбаум = дубль, новую не создаёт."""
    _, c1 = await _gate_cam(db, "КПП", "Двор", 1, "cam1")
    _, r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0, cam=c1.id)
    _, r2 = await _emit(
        db, "123ABC02", Direction.ENTRY, T0 + timedelta(seconds=5), cam=c1.id
    )
    assert r1.action == "created"
    assert r2.action == "entry_restarted"
    assert r2.session_id == r1.session_id
