"""Payment Service — платежи за парковочные сессии через провайдера (в MVP — mock).

Поток: создать платёж (pending) -> провайдер выдаёт ссылку -> оплата подтверждается
webhook'ом -> платёж paid + сессия paid. Провайдер — заглушка (см. payment_provider).
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models import ParkingSession, Payment, PaymentStatus, SessionStatus
from src.modules.payment_provider import MockPaymentProvider, PaymentProvider
from src.schemas import (
    BillingStatsOut,
    PaymentCreate,
    PaymentOut,
    PaymentWebhook,
)

# Активный провайдер оплаты. Чтобы подключить реального — подставь его здесь.
provider: PaymentProvider = MockPaymentProvider()


async def create_payment_for_session(
    session: AsyncSession, parking: ParkingSession
) -> Payment:
    """Создать платёж по сессии (сумма = стоимость сессии)."""
    amount = parking.price or 0.0
    currency = "KZT"
    pp = provider.create(amount, currency, reference=f"session-{parking.id}")
    payment = Payment(
        session_id=parking.id,
        amount=amount,
        currency=currency,
        status=PaymentStatus.PENDING,
        provider=provider.name,
        provider_payment_id=pp.provider_payment_id,
        pay_url=pp.pay_url,
    )
    session.add(payment)
    await session.flush()
    return payment


async def mark_paid_by_provider_id(
    session: AsyncSession, provider_payment_id: str
) -> Payment | None:
    """Подтвердить оплату (webhook): платёж -> paid, сессия -> paid. Идемпотентно."""
    result = await session.execute(
        select(Payment).where(Payment.provider_payment_id == provider_payment_id)
    )
    payment = result.scalars().first()
    if payment is None:
        return None
    if payment.status == PaymentStatus.PAID:
        return payment  # уже оплачено — идемпотентно, дубля не создаём
    payment.status = PaymentStatus.PAID
    payment.paid_at = datetime.now(timezone.utc)
    parking = await session.get(ParkingSession, payment.session_id)
    if parking is not None:
        parking.status = SessionStatus.PAID
    await session.flush()
    return payment


# --------------------------------------------------------------------------- #
# HTTP API — создание платежа, статус, webhook
# --------------------------------------------------------------------------- #

router = APIRouter(prefix="/api/v1", tags=["payments"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/payments/create", response_model=PaymentOut, status_code=201)
async def create_payment(payload: PaymentCreate, session: SessionDep) -> PaymentOut:
    """Создать платёж для парковочной сессии."""
    parking = await session.get(ParkingSession, payload.session_id)
    if parking is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    payment = await create_payment_for_session(session, parking)
    await session.refresh(payment)
    return PaymentOut.model_validate(payment)


@router.get("/payments/status/{payment_id}", response_model=PaymentOut)
async def payment_status(payment_id: int, session: SessionDep) -> PaymentOut:
    """Статус платежа по id."""
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    return PaymentOut.model_validate(payment)


@router.post("/payments/webhook", response_model=PaymentOut)
async def payment_webhook(payload: PaymentWebhook, session: SessionDep) -> PaymentOut:
    """Уведомление об оплате от провайдера (в MVP дёргается из Студии)."""
    payment = await mark_paid_by_provider_id(session, payload.provider_payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    await session.refresh(payment)
    return PaymentOut.model_validate(payment)


@router.get("/dashboard/billing", response_model=BillingStatsOut)
async def billing_stats(session: SessionDep) -> BillingStatsOut:
    """Агрегации для дашборда денег (итерация 7)."""
    today_start = datetime.combine(
        datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc
    )
    revenue = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
                Payment.status == PaymentStatus.PAID,
                Payment.paid_at >= today_start,
            )
        )
    ).scalar_one()
    unpaid = (
        await session.execute(
            select(func.count())
            .select_from(ParkingSession)
            .where(ParkingSession.status == SessionStatus.UNPAID)
        )
    ).scalar_one()
    avg_sec = (
        await session.execute(
            select(func.avg(ParkingSession.duration_seconds)).where(
                ParkingSession.duration_seconds.is_not(None)
            )
        )
    ).scalar_one()
    return BillingStatsOut(
        revenue_today=float(revenue),
        unpaid_count=int(unpaid),
        avg_parked_seconds=int(avg_sec) if avg_sec is not None else None,
    )
