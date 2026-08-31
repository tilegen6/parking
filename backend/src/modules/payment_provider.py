"""Провайдер оплаты — интерфейс + MOCK-заглушка (легко удалить/заменить).

MockPaymentProvider имитирует внешнего провайдера (Kaspi Pay / Freedom Pay) без
реальной оплаты: выдаёт id платежа и ссылку, а «оплата» подтверждается вызовом
webhook из Студии/фронта. Никаких секретов, HTTPS и реального провайдера не нужно.

Чтобы подключить реального провайдера:
  1) реализуй класс по протоколу PaymentProvider (метод create),
  2) подставь его в src/modules/payment.py вместо MockPaymentProvider,
  3) удали этот файл (или оставь mock для локальных тестов).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


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
