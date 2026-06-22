"""Точка входа FastAPI-приложения Smart Parking ANPR."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.config import settings
from src.database import engine
from src.modules import camera, recognition
from src.storage import storage

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smart_parking")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Запуск %s (env=%s)", settings.app_name, settings.app_env)
    # Подготовить bucket MinIO (не падаем, если MinIO недоступен)
    try:
        storage.ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        logger.warning("MinIO недоступен при старте: %s", exc)
    yield
    await engine.dispose()
    logger.info("Остановка приложения")


app = FastAPI(
    title=settings.app_name,
    description="Backend системы умной парковки: приём ANPR-событий Hikvision.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Глобальный обработчик: backend не падает на неожиданных ошибках."""
    logger.exception("Необработанная ошибка на %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"},
    )


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Health check для DevOps / Nginx / Docker."""
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}


app.include_router(recognition.router)
app.include_router(camera.router)
app.include_router(camera.dashboard_router)
