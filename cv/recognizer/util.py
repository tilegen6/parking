"""Мелкие утилиты, общие для движков (сеть/сертификаты)."""

from __future__ import annotations

import os


def ensure_ssl_certs() -> None:
    """macOS python.org-сборка не ставит корневые сертификаты, из-за чего загрузка
    моделей (EasyOCR/YOLO) падает с SSL CERTIFICATE_VERIFY_FAILED. Подставляем certifi.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except ImportError:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
