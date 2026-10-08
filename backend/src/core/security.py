"""Безопасность входящих запросов Kaspi (онлайн-протокол провайдера).

Kaspi шлёт запросы с фиксированных IP-подсетей (Протокол взаимодействия, п.1).
Проверяем источник по allowlist, опционально — Basic Auth поверх него. За nginx
реальный IP берём из первого узла X-Forwarded-For.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import HTTPException, Request, status

from src.config import settings


def _client_ip(request: Request) -> str | None:
    """Реальный IP клиента: первый узел X-Forwarded-For (за nginx) либо peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _check_basic_auth(request: Request) -> bool:
    """True, если Basic Auth не настроена или совпала с ожидаемой."""
    if not settings.kaspi_provider_username:
        return True  # Basic Auth не требуется — достаточно IP-allowlist
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic" or not token:
        return False
    try:
        decoded = base64.b64decode(token).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, _, password = decoded.partition(":")
    return (
        user == settings.kaspi_provider_username
        and password == settings.kaspi_provider_password
    )


async def verify_kaspi_source(request: Request) -> None:
    """FastAPI-зависимость: пропускает только доверенные запросы Kaspi.

    403, если IP вне allowlist или Basic Auth не прошла. Пустой allowlist =
    проверка IP отключена (например, для локальной отладки).
    """
    allowed = settings.kaspi_allowed_ips_list
    if allowed:
        ip = _client_ip(request)
        if ip not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="IP не в списке разрешённых Kaspi",
            )
    if not _check_basic_auth(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Неверная Basic Auth"
        )
