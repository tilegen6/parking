"""Тесты списков доступа: резолвер, CRUD-гварды, шлагбаум по спискам, алерты."""

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select

from src.models import (
    AccessEntry,
    AccessListType,
    Alert,
    AuditLog,
    Camera,
    Direction,
    Gate,
    ParkingSession,
    RecognitionEvent,
    SessionStatus,
    Tariff,
    User,
    UserRole,
)
from src.modules import access, auth
from src.modules import session as svc

T0 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


# ── Резолвер (юнит) ─────────────────────────────────────────────────────────


def test_normalize_plate():
    assert access.normalize_plate(" 127 ast-02 ") == "127AST02"
    assert access.normalize_plate(None) == ""


def test_normalize_plate_transliterates_cyrillic():
    """Казахстанские номера часто приходят кириллицей-гомоглифами (А, В, Е, К,
    М, Н, О, Р, С, Т, У, Х). Без транслитерации они вырезались бы как не-ASCII
    и номер превращался в пустую строку → машина не находила свою сессию."""
    # чистая кириллица, визуально совпадающая с латиницей
    assert access.normalize_plate("777АВС02") == "777ABC02"
    assert access.normalize_plate("О123РТ77") == "O123PT77"
    # смешанный ввод (часть латиницей, часть кириллицей) сходится к одному виду
    assert access.normalize_plate("777АBC02") == access.normalize_plate("777ABC02")
    # строчная кириллица тоже
    assert access.normalize_plate("м100мм") == "M100MM"


def test_normalize_plate_all_cyrillic_stays_nonempty():
    """Гомоглифы транслитерируются, а не выкидываются — результат не пустой."""
    assert access.normalize_plate("АВЕКМНОРСТУХ") == "ABEKMHOPCTYX"


async def test_resolver_gate_specific_beats_global(db):
    g = Gate(name="КПП")
    db.add(g)
    await db.flush()
    db.add_all(
        [
            AccessEntry(
                plate="127AST02", list_type=AccessListType.YELLOW, gate_id=None
            ),
            AccessEntry(plate="127AST02", list_type=AccessListType.GREEN, gate_id=g.id),
        ]
    )
    await db.flush()
    eff = await access.resolve_access(db, "127AST02", g.id)
    assert eff is not None and eff.list_type == AccessListType.GREEN  # спец > глобал


async def test_resolver_red_wins_on_same_level(db):
    db.add_all(
        [
            AccessEntry(plate="127AST02", list_type=AccessListType.GREEN, gate_id=None),
            AccessEntry(plate="127AST02", list_type=AccessListType.RED, gate_id=None),
        ]
    )
    await db.flush()
    eff = await access.resolve_access(db, "127AST02", None)
    assert eff is not None and eff.list_type == AccessListType.RED


async def test_resolver_none_when_no_match(db):
    assert await access.resolve_access(db, "999ZZZ09", None) is None


# ── Шлагбаум по спискам (через обработку событий) ───────────────────────────


async def _gate_cam(db, cam_name="cam1"):
    g = Gate(name="КПП двор", zone="Двор", level=1)
    db.add(g)
    await db.flush()
    cam = Camera(name=cam_name, gate_id=g.id)
    db.add(cam)
    await db.flush()
    return g, cam


async def _emit(db, plate, direction, t, cam_id=None):
    ev = RecognitionEvent(
        plate_number=plate,
        direction=direction,
        event_time=t,
        confidence=0.95,
        camera_id=cam_id,
    )
    db.add(ev)
    await db.flush()
    return ev, await svc.handle_recognition_event(db, ev)


async def test_red_list_denies_and_alerts(db):
    g, cam = await _gate_cam(db)
    db.add(AccessEntry(plate="666RED66", list_type=AccessListType.RED, gate_id=g.id))
    await db.flush()

    ev, r = await _emit(db, "666RED66", Direction.ENTRY, T0, cam.id)
    assert r.action == "access_denied_red"
    assert ev.flag == "access_denied_red"
    # сессия НЕ создана
    total = (
        await db.execute(select(func.count()).select_from(ParkingSession))
    ).scalar_one()
    assert total == 0
    # оповещение записано
    alerts = (await db.execute(select(Alert))).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].plate == "666RED66"


async def test_green_list_free_exit(db):
    g, cam = await _gate_cam(db)
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=200, daily_cap=None, is_active=True
        )
    )
    db.add(AccessEntry(plate="911GRN11", list_type=AccessListType.GREEN, gate_id=g.id))
    await db.flush()

    _, r1 = await _emit(db, "911GRN11", Direction.ENTRY, T0, cam.id)
    assert r1.action == "created"
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.access_type == "green"

    # выезд через 3 часа — бесплатно, шлагбаум открыт
    _, rx = await _emit(db, "911GRN11", Direction.EXIT, T0 + timedelta(hours=3), cam.id)
    assert rx.action == "closed"
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.status == SessionStatus.PAID
    assert sess.price == 0.0


async def test_yellow_free_until_then_charged(db):
    g, cam = await _gate_cam(db)
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=200, daily_cap=None, is_active=True
        )
    )
    # бесплатно до T0+2ч
    db.add(
        AccessEntry(
            plate="777YEL77",
            list_type=AccessListType.YELLOW,
            gate_id=g.id,
            valid_until=T0 + timedelta(hours=2),
        )
    )
    await db.flush()

    _, r1 = await _emit(db, "777YEL77", Direction.ENTRY, T0, cam.id)
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.access_type == "yellow"

    # выезд в пределах бесплатного окна — бесплатно
    _, rin = await _emit(
        db, "777YEL77", Direction.EXIT, T0 + timedelta(hours=1), cam.id
    )
    assert rin.action == "closed"
    assert (await db.get(ParkingSession, r1.session_id)).price == 0.0


async def test_yellow_overstay_is_charged(db):
    g, cam = await _gate_cam(db)
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=200, daily_cap=None, is_active=True
        )
    )
    db.add(
        AccessEntry(
            plate="777YEL77",
            list_type=AccessListType.YELLOW,
            gate_id=g.id,
            valid_until=T0 + timedelta(hours=2),
        )
    )
    await db.flush()
    await _emit(db, "777YEL77", Direction.ENTRY, T0, cam.id)
    # выезд через 3ч: перебор 1ч сверх бесплатного окна -> 200, долг -> шлагбаум закрыт
    _, rx = await _emit(db, "777YEL77", Direction.EXIT, T0 + timedelta(hours=3), cam.id)
    assert rx.action == "exit_denied_unpaid"
    assert rx.detail == "due=200"


# ── CRUD-гварды + аудит + алерты API ────────────────────────────────────────


@pytest_asyncio.fixture
async def manager_token(client, db):
    db.add(
        User(
            username="mgr",
            password_hash=auth.hash_password("mgrpass1"),
            role=UserRole.LIST_MANAGER,
        )
    )
    await db.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"username": "mgr", "password": "mgrpass1"}
    )
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


async def test_access_crud_requires_auth(client):
    r = await client.post(
        "/api/v1/access-entries", json={"plate": "1", "list_type": "green"}
    )
    assert r.status_code in (401, 403)


async def test_access_crud_with_manager_and_audit(client, manager_token, db):
    r = await client.post(
        "/api/v1/access-entries",
        headers=_h(manager_token),
        json={"plate": "127ast02", "list_type": "green", "note": "сотрудник"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["plate"] == "127AST02"  # нормализован
    assert body["created_by_username"] == "mgr"
    eid = body["id"]

    r = await client.get("/api/v1/access-entries", headers=_h(manager_token))
    assert any(e["id"] == eid for e in r.json())

    r = await client.delete(f"/api/v1/access-entries/{eid}", headers=_h(manager_token))
    assert r.status_code == 204

    # аудит зафиксировал create + delete (проверяем в БД — /audit-log только admin)
    actions = [a.action for a in (await db.execute(select(AuditLog))).scalars().all()]
    assert "access.create" in actions
    assert "access.delete" in actions


async def test_operator_cannot_manage_lists(client, db):
    db.add(
        User(
            username="op2",
            password_hash=auth.hash_password("op2pass1"),
            role=UserRole.OPERATOR,
        )
    )
    await db.commit()
    tok = (
        await client.post(
            "/api/v1/auth/login", json={"username": "op2", "password": "op2pass1"}
        )
    ).json()["access_token"]
    r = await client.post(
        "/api/v1/access-entries",
        headers=_h(tok),
        json={"plate": "1", "list_type": "green"},
    )
    assert r.status_code == 403  # оператор не ведёт списки


async def test_alerts_list_and_ack(client, manager_token, db):
    db.add(Alert(kind="red_list", plate="666RED66", message="тест"))
    await db.commit()
    r = await client.get("/api/v1/alerts", headers=_h(manager_token))
    assert len(r.json()) == 1
    aid = r.json()[0]["id"]
    ack = await client.post(f"/api/v1/alerts/{aid}/ack", headers=_h(manager_token))
    assert ack.json()["acknowledged"] is True
    # после подтверждения в списке «только новые» его нет
    r2 = await client.get("/api/v1/alerts", headers=_h(manager_token))
    assert r2.json() == []
