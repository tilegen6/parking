"""Тесты Kaspi AutomaticPayments: клиент (MockTransport) + хук автосписания."""

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select

from src.integrations.kaspi_autopay import AutoPayResult, KaspiAutoPayClient
from src.models import (
    Direction,
    ParkingSession,
    Payment,
    PaymentStatus,
    RecognitionEvent,
    SessionStatus,
    Tariff,
)
from src.modules import session as svc

T0 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)


def _client(handler) -> KaspiAutoPayClient:
    return KaspiAutoPayClient(
        username="u", password="p", transport=httpx.MockTransport(handler)
    )


# --- Клиент (исходящие запросы к Kaspi) ----------------------------------- #


async def test_enter_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/parking/enter"
        return httpx.Response(200, json={"isSuccess": True, "data": {"requestId": "x"}})

    res = await _client(handler).enter("123ABC02", 1)
    assert res.is_success


async def test_exit_success_parses_transaction_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/parking/exit"
        return httpx.Response(
            200,
            json={
                "isSuccess": True,
                "data": {"transactionId": "777", "requestId": "x"},
            },
        )

    res = await _client(handler).exit("123ABC02", 200.0, 1)
    assert res.is_success
    assert res.transaction_id == "777"


async def test_exit_user_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "isSuccess": False,
                "error": {"code": "USER_NOT_FOUND", "message": "m"},
            },
        )

    res = await _client(handler).exit("123ABC02", 200.0, 1)
    assert not res.is_success
    assert res.error_code == "USER_NOT_FOUND"


async def test_exit_insufficient_funds():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "isSuccess": False,
                "error": {"code": "INSUFFICIENT_FUNDS", "message": "нет средств"},
            },
        )

    res = await _client(handler).exit("123ABC02", 200.0, 1)
    assert res.error_code == "INSUFFICIENT_FUNDS"


async def test_timeout_returns_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    res = await _client(handler).exit("123ABC02", 200.0, 1)
    assert not res.is_success
    assert res.error_code == "TIMEOUT"


# --- Хук автосписания в session-сервисе (EXIT) ---------------------------- #


def _fake_autopay(result: AutoPayResult):
    class _Fake:
        def __init__(self, *a, **k):
            pass

        async def enter(self, *a, **k):
            return AutoPayResult(True, "rid")

        async def exit(self, *a, **k):
            return result

    return _Fake


async def _emit(db, plate, direction, t):
    event = RecognitionEvent(
        plate_number=plate, direction=direction, event_time=t, confidence=0.95
    )
    db.add(event)
    await db.flush()
    return await svc.handle_recognition_event(db, event)


async def _seed_tariff(db):
    db.add(
        Tariff(
            name="t", free_minutes=0, price_per_hour=100, daily_cap=None, is_active=True
        )
    )
    await db.flush()


async def test_autopay_success_releases_on_exit(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "kaspi_autopay_enabled", True)
    monkeypatch.setattr(
        svc, "KaspiAutoPayClient", _fake_autopay(AutoPayResult(True, "rid", "T1"))
    )
    await _seed_tariff(db)
    r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    r3 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    assert r3.action == "closed"  # автосписание прошло → выпустили
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.status == SessionStatus.PAID
    assert sess.paid_amount == 200
    paid = (
        await db.execute(
            select(func.count())
            .select_from(Payment)
            .where(Payment.provider == "kaspi_autopay")
        )
    ).scalar_one()
    assert paid == 1


async def test_autopay_user_not_found_falls_back_to_manual(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "kaspi_autopay_enabled", True)
    monkeypatch.setattr(
        svc,
        "KaspiAutoPayClient",
        _fake_autopay(AutoPayResult(False, "rid", error_code="USER_NOT_FOUND")),
    )
    await _seed_tariff(db)
    r1 = await _emit(db, "123ABC02", Direction.ENTRY, T0)
    r3 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    assert r3.action == "exit_denied_unpaid"  # нет автосписания → ручная оплата
    sess = await db.get(ParkingSession, r1.session_id)
    assert sess.status == SessionStatus.ACTIVE


async def test_autopay_declined_denies_and_records_failure(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "kaspi_autopay_enabled", True)
    monkeypatch.setattr(
        svc,
        "KaspiAutoPayClient",
        _fake_autopay(AutoPayResult(False, "rid", error_code="INSUFFICIENT_FUNDS")),
    )
    await _seed_tariff(db)
    await _emit(db, "123ABC02", Direction.ENTRY, T0)
    r3 = await _emit(db, "123ABC02", Direction.EXIT, T0 + timedelta(hours=2))
    assert r3.action == "exit_denied_unpaid"
    failed = (
        (
            await db.execute(
                select(Payment).where(Payment.status == PaymentStatus.FAILED)
            )
        )
        .scalars()
        .first()
    )
    assert failed is not None
    assert failed.error_code == "INSUFFICIENT_FUNDS"
