"""Kaspi онлайн-протокол провайдера (входящий, Kaspi -> нас).

Kaspi дёргает единый эндпоинт GET /api/kaspi/pay с параметром command:

  * command=check — проверка: есть ли по номеру авто (account) неоплаченная
    сессия и на какую сумму. Возвращаем result=0 + sum, либо result=1.
  * command=pay   — оплата: кредитуем сессию, создаём Payment(provider=kaspi),
    возвращаем result=0 + prv_txn (id нашего платежа). Идемпотентно по txn_id
    (повтор с тем же txn_id → result=3, без двойного списания; Протокол §7).

Ответ — XML (по спецификации) или JSON, коды result 0/1/2/3/4/5 (Протокол §9).
Доступ ограничен IP-allowlist Kaspi (см. core.security.verify_kaspi_source).

Дополнительно — внутренний DEBUG-эндпоинт для теста автосписания из Студии.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.security import verify_kaspi_source
from src.database import get_session
from src.models import Payment, PaymentStatus
from src.modules.access import normalize_plate
from src.modules.payment import amount_due, credit_session
from src.modules.session import find_active_session

logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# --- Коды результата (Протокол взаимодействия, §9) ------------------------- #
class KaspiResult:
    OK = 0  # найдено и доступно для оплаты
    NOT_FOUND = 1  # абонент/счёт/заказ не найден
    CANCELLED = 2  # заказ отменён
    ALREADY_PAID = 3  # уже оплачено
    PROCESSING = 4  # платёж в обработке
    ERROR = 5  # другая ошибка провайдера


def _fmt_sum(value: float) -> str:
    """Сумма с точностью до сотых и точкой-разделителем (например «200.00»)."""
    return f"{value:.2f}"


def _render(data: dict[str, Any], fmt: str) -> Response:
    """Сериализовать ответ провайдера в XML (по умолчанию) или JSON. Всегда 200."""
    if fmt == "json":
        payload = {"txn_id": data["txn_id"], "result": data["result"]}
        if "sum" in data:
            payload["sum"] = data["sum"]
        if "prv_txn" in data:
            payload["prv_txn_id"] = data["prv_txn"]
        payload["comment"] = data.get("comment", "")
        return Response(content=json.dumps(payload), media_type="application/json")

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<response>",
        f"  <txn_id>{escape(str(data['txn_id']))}</txn_id>",
        f"  <result>{int(data['result'])}</result>",
    ]
    if "prv_txn" in data:
        parts.append(f"  <prv_txn>{escape(str(data['prv_txn']))}</prv_txn>")
    if "sum" in data:
        parts.append(f"  <sum>{escape(str(data['sum']))}</sum>")
    parts.append(f"  <comment>{escape(data.get('comment', ''))}</comment>")
    parts.append("</response>")
    return Response(content="\n".join(parts), media_type="application/xml")


router = APIRouter(prefix="/api/kaspi", tags=["kaspi"])


@router.get("/pay", dependencies=[Depends(verify_kaspi_source)])
async def kaspi_pay(
    session: SessionDep,
    command: str = Query(..., description="check | pay"),
    txn_id: str = Query(..., max_length=64, description="ID запроса в системе Kaspi"),
    account: str = Query(..., description="Идентификатор абонента — номер авто"),
    sum: str | None = Query(None, description="Сумма платежа (для pay)"),
    txn_date: str | None = Query(None, description="Дата учёта платежа (для pay)"),
    format: str | None = Query(
        None, description="xml | json — переопределить формат ответа (для отладки)"
    ),
) -> Response:
    """Единая точка онлайн-протокола Kaspi: диспетчер по command (check|pay)."""
    fmt = format or settings.kaspi_provider_response_format
    # Kaspi присылает номер как ввёл водитель — канонизируем так же, как события
    # камеры, иначе lookup активной сессии не совпадёт.
    plate = normalize_plate(account)

    if command == "check":
        return await _handle_check(session, txn_id, plate, fmt)
    if command == "pay":
        return await _handle_pay(session, txn_id, plate, sum, fmt)

    logger.warning("Kaspi: неизвестный command=%s", command)
    return _render(
        {"txn_id": txn_id, "result": KaspiResult.ERROR, "comment": "unknown command"},
        fmt,
    )


async def _handle_check(
    session: AsyncSession, txn_id: str, plate: str, fmt: str
) -> Response:
    """check: вернуть сумму долга по номеру авто либо «не найдено»."""
    parking = await find_active_session(session, plate)
    if parking is None:
        return _render({"txn_id": txn_id, "result": KaspiResult.NOT_FOUND}, fmt)
    due = await amount_due(session, parking)
    if due <= 0:
        # Машина на парковке, но платить нечего (бесплатно/уже оплачено)
        return _render({"txn_id": txn_id, "result": KaspiResult.NOT_FOUND}, fmt)
    return _render(
        {"txn_id": txn_id, "result": KaspiResult.OK, "sum": _fmt_sum(due)}, fmt
    )


async def _handle_pay(
    session: AsyncSession, txn_id: str, plate: str, sum_raw: str | None, fmt: str
) -> Response:
    """pay: идемпотентно провести оплату по txn_id и кредитовать сессию."""
    # Идемпотентность: повтор с тем же txn_id → прежний результат (Протокол §7)
    existing = (
        (
            await session.execute(
                select(Payment).where(
                    Payment.provider == "kaspi",
                    Payment.provider_payment_id == txn_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return _render(
            {
                "txn_id": txn_id,
                "result": KaspiResult.ALREADY_PAID,
                "prv_txn": existing.id,
                "sum": _fmt_sum(existing.amount),
            },
            fmt,
        )

    parking = await find_active_session(session, plate)
    if parking is None:
        return _render({"txn_id": txn_id, "result": KaspiResult.NOT_FOUND}, fmt)

    try:
        amount = float(sum_raw) if sum_raw is not None else 0.0
    except ValueError:
        return _render(
            {"txn_id": txn_id, "result": KaspiResult.ERROR, "comment": "bad sum"}, fmt
        )
    if amount <= 0:
        amount = await amount_due(session, parking)

    payment = Payment(
        session_id=parking.id,
        amount=amount,
        currency="KZT",
        status=PaymentStatus.PAID,
        provider="kaspi",
        provider_payment_id=txn_id,
        paid_at=datetime.now(timezone.utc),
    )
    session.add(payment)
    await credit_session(session, parking.id, amount)
    try:
        await session.flush()
    except IntegrityError:
        # Гонка одновременных pay с одним txn_id — не задваиваем (Протокол §7)
        await session.rollback()
        existing = (
            (
                await session.execute(
                    select(Payment).where(
                        Payment.provider == "kaspi",
                        Payment.provider_payment_id == txn_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        prv = existing.id if existing else txn_id
        amt = existing.amount if existing else amount
        return _render(
            {
                "txn_id": txn_id,
                "result": KaspiResult.ALREADY_PAID,
                "prv_txn": prv,
                "sum": _fmt_sum(amt),
            },
            fmt,
        )

    logger.info(
        "Kaspi pay: сессия #%s (%s) оплачена на %.2f, txn_id=%s",
        parking.id,
        plate,
        amount,
        txn_id,
    )
    return _render(
        {
            "txn_id": txn_id,
            "result": KaspiResult.OK,
            "prv_txn": payment.id,
            "sum": _fmt_sum(amount),
            "comment": "OK",
        },
        fmt,
    )


# --------------------------------------------------------------------------- #
# Внутренний DEBUG-эндпоинт: тест автосписания (Kaspi AutomaticPayments) из UI
# --------------------------------------------------------------------------- #

debug_router = APIRouter(prefix="/api/v1", tags=["kaspi-debug"])


@debug_router.get("/kaspi/info")
async def kaspi_info() -> dict[str, Any]:
    """Публичный статус интеграции Kaspi для Студии (без секретов)."""
    return {
        "payment_provider": settings.payment_provider,
        "provider_enabled": settings.kaspi_provider_enabled,
        "autopay_enabled": settings.kaspi_autopay_enabled,
    }


@debug_router.post("/kaspi/autopay/simulate-exit")
async def simulate_autopay_exit(
    session: SessionDep,
    request: Request,
) -> dict[str, Any]:
    """Пробный вызов Kaspi exit по сессии (для Студии). Только при DEBUG.

    Не мутирует сессию — показывает, что вернул бы Kaspi. Если creds не заданы,
    вызов к autopayments.kaspi.kz ожидаемо не пройдёт — вернём его результат как есть.
    """
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    body = await request.json()
    session_id = int(body.get("session_id", 0))

    from src.models import ParkingSession

    parking = await session.get(ParkingSession, session_id)
    if parking is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    due = await amount_due(session, parking)

    from src.integrations.kaspi_autopay import KaspiAutoPayClient

    result = await KaspiAutoPayClient().exit(parking.plate_number, due, parking.id)
    return {
        "session_id": parking.id,
        "plate": parking.plate_number,
        "amount": due,
        "is_success": result.is_success,
        "transaction_id": result.transaction_id,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "autopay_enabled": settings.kaspi_autopay_enabled,
    }
