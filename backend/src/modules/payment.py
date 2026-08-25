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

from src.config import settings
from src.database import get_session
from src.models import ParkingSession, Payment, PaymentStatus, SessionStatus
from src.modules.payment_provider import (
    KaspiOnlineProvider,
    MockPaymentProvider,
    PaymentProvider,
)
from src.modules.tariff import get_active_tariff, tariff_price
from src.schemas import (
    BillingStatsOut,
    PaymentCreate,
    PaymentOut,
    PaymentWebhook,
)


def _select_provider() -> PaymentProvider:
    """Активный провайдер оплаты по настройке PAYMENT_PROVIDER (mock | kaspi)."""
    if settings.payment_provider == "kaspi":
        return KaspiOnlineProvider()
    return MockPaymentProvider()


provider: PaymentProvider = _select_provider()


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def amount_due(session: AsyncSession, parking: ParkingSession) -> float:
    """Сколько сейчас должна сессия: цена за время стоянки минус уже оплачено.

    Для активной берём «сейчас», для выехавшей — exit_time.
    """
    tariff = await get_active_tariff(session)
    entry = _aware(parking.entry_time)
    ref = _aware(parking.exit_time) or datetime.now(timezone.utc)
    duration = int((ref - entry).total_seconds()) if entry is not None else 0
    price = tariff_price(duration, tariff)
    return round(max(0.0, price - (parking.paid_amount or 0.0)), 2)


async def create_payment_for_session(
    session: AsyncSession, parking: ParkingSession
) -> Payment:
    """Создать платёж на ТЕКУЩИЙ долг сессии (цена сейчас − уже оплачено)."""
    due = await amount_due(session, parking)
    if due <= 0:
        raise HTTPException(status_code=400, detail="По сессии нечего оплачивать")
    pp = provider.create(due, "KZT", reference=f"session-{parking.id}")
    payment = Payment(
        session_id=parking.id,
        amount=due,
        currency="KZT",
        status=PaymentStatus.PENDING,
        provider=provider.name,
        provider_payment_id=pp.provider_payment_id,
        pay_url=pp.pay_url,
    )
    session.add(payment)
    await session.flush()
    return payment


async def credit_session(
    session: AsyncSession, session_id: int, amount: float
) -> ParkingSession | None:
    """Зачислить оплату в сессию: копим paid_amount; выехавшую переводим в paid.

    Общий помощник для webhook (mock) и входящего Kaspi-протокола (modules/kaspi).
    """
    parking = await session.get(ParkingSession, session_id)
    if parking is not None:
        parking.paid_amount = round((parking.paid_amount or 0.0) + amount, 2)
        # Если уже выехал и теперь оплата покрыла долг — статус paid
        if parking.exit_time is not None:
            parking.status = SessionStatus.PAID
    return parking


async def mark_paid_by_provider_id(
    session: AsyncSession, provider_payment_id: str
) -> Payment | None:
    """Подтвердить оплату (webhook): платёж -> paid, копим paid_amount. Идемпотентно."""
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
    await credit_session(session, payment.session_id, payment.amount)
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
