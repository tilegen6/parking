"""Провайдеры оплаты — интерфейс + реализации (mock и Kaspi онлайн).

MockPaymentProvider имитирует внешнего провайдера без реальной оплаты: выдаёт id
платежа и ссылку, а «оплата» подтверждается вызовом webhook из Студии/фронта.

KaspiOnlineProvider — реальный Kaspi.kz (онлайн-протокол провайдера). create()
формирует ссылку/QR (deeplink) на оплату в приложении Kaspi; само подтверждение
оплаты приходит ВХОДЯЩИМ запросом Kaspi на GET /api/kaspi/pay (см. modules/kaspi).

Активный провайдер выбирается в src/modules/payment.py по settings.payment_provider.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from src.config import settings


@dataclass
class ProviderPayment:
    """Ответ провайдера при создании платежа."""

    provider_payment_id: str
    pay_url: str


class PaymentProvider(Protocol):
    name: str

    def create(
        self, amount: float, currency: str, reference: str
    ) -> ProviderPayment: ...


class MockPaymentProvider:
    """Фейковый провайдер: оплата подтверждается webhook'ом из Студии."""

    name = "mock"

    def create(self, amount: float, currency: str, reference: str) -> ProviderPayment:
        pid = f"mock_{uuid.uuid4().hex[:16]}"
        # pay_url — куда «пошёл бы» пользователь; в mock его дёргает Студия
        return ProviderPayment(provider_payment_id=pid, pay_url=f"/pay/{pid}")


class KaspiOnlineProvider:
    """Реальный Kaspi.kz (онлайн-протокол провайдера).

    create() отдаёт deeplink/QR на оплату в приложении Kaspi (шаблон из настроек,
    {account} = референс сессии). Подтверждение приходит ВХОДЯЩИМ запросом Kaspi
    на /api/kaspi/pay — он и кредитует сессию, здесь платёж только инициируется.
    """

    name = "kaspi"

    def create(self, amount: float, currency: str, reference: str) -> ProviderPayment:
        pid = f"kaspi_{uuid.uuid4().hex[:16]}"
        template = settings.kaspi_pay_deeplink_template
        pay_url = (
            template.replace("{account}", reference) if template else f"/pay/{pid}"
        )
        return ProviderPayment(provider_payment_id=pid, pay_url=pay_url)
