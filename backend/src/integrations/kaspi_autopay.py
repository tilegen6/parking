"""Kaspi AutomaticPayments — исходящий клиент автосписания (мы -> Kaspi).

Реализует POST /api/parking/enter и /api/parking/exit (host autopayments.kaspi.kz)
с Basic Auth. Используется в session-сервисе: enter — при въезде (регистрация
сессии + бесплатное время), exit — при выезде для автосписания с карты водителя.

Ответ Kaspi: {"isSuccess": bool, "data": {...} | "error": {"code","message"}}.
Клиент не бросает исключения наружу — сетевые/HTTP-ошибки превращаются в
AutoPayResult(is_success=False) с кодом ошибки, чтобы приём событий не падал.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AutoPayResult:
    """Разобранный ответ Kaspi на enter/exit."""

    is_success: bool
    request_id: str
    transaction_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _request_date() -> str:
    """Время запроса для Kaspi (ISO-8601, UTC)."""
    return datetime.now(timezone.utc).isoformat()


class KaspiAutoPayClient:
    """Клиент Kaspi AutomaticPayments. Параметры по умолчанию — из настроек.

    ``transport`` позволяет подставить httpx.MockTransport в тестах (без сети).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
        parking_id: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or settings.kaspi_autopay_base_url).rstrip("/")
        self._auth = (
            username if username is not None else settings.kaspi_autopay_username,
            password if password is not None else settings.kaspi_autopay_password,
        )
        self._timeout = timeout or settings.kaspi_http_timeout_seconds
        self._parking_id = (
            parking_id if parking_id is not None else settings.kaspi_parking_id
        )
        self._transport = transport

    async def _post(
        self, path: str, payload: dict[str, Any], request_id: str
    ) -> AutoPayResult:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                auth=self._auth,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(path, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException:
            logger.warning("Kaspi autopay таймаут: %s", path)
            return AutoPayResult(False, request_id, error_code="TIMEOUT")
        except httpx.HTTPError as exc:
            logger.warning("Kaspi autopay ошибка запроса %s: %s", path, exc)
            return AutoPayResult(False, request_id, error_code="SYSTEM_ERROR")
        except ValueError:  # невалидный JSON
            logger.warning("Kaspi autopay: невалидный JSON в ответе %s", path)
            return AutoPayResult(False, request_id, error_code="SYSTEM_ERROR")

        return self._parse(body, request_id)

    @staticmethod
    def _parse(body: dict[str, Any], request_id: str) -> AutoPayResult:
        if body.get("isSuccess"):
            data = body.get("data") or {}
            return AutoPayResult(
                True,
                request_id,
                transaction_id=(
                    str(data["transactionId"]) if "transactionId" in data else None
                ),
            )
        error = body.get("error") or {}
        return AutoPayResult(
            False,
            request_id,
            error_code=error.get("code"),
            error_message=error.get("message"),
        )

    async def enter(
        self,
        car_plate: str,
        parking_session_id: str | int,
        *,
        request_id: str | None = None,
        free_time: int | None = None,
    ) -> AutoPayResult:
        """POST /api/parking/enter — зарегистрировать въезд и бесплатное время."""
        rid = request_id or uuid.uuid4().hex
        payload = {
            "parkingId": self._parking_id,
            "carPlate": car_plate,
            "requestId": rid,
            "requestDate": _request_date(),
            "parkingSessionId": str(parking_session_id),
            "freeTime": (
                free_time if free_time is not None else settings.kaspi_free_time_seconds
            ),
        }
        return await self._post("/api/parking/enter", payload, rid)

    async def exit(
        self,
        car_plate: str,
        amount: float,
        parking_session_id: str | int,
        *,
        request_id: str | None = None,
    ) -> AutoPayResult:
        """POST /api/parking/exit — списать сумму с привязанной карты водителя."""
        rid = request_id or uuid.uuid4().hex
        payload = {
            "parkingId": self._parking_id,
            "carPlate": car_plate,
            "amount": amount,
            "requestId": rid,
            "requestDate": _request_date(),
            "parkingSessionId": str(parking_session_id),
        }
        return await self._post("/api/parking/exit", payload, rid)
