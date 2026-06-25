"""Точка входа FastAPI-приложения Smart Parking."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

# CORS: разрешаем запросы только с origin'ов фронтенда из .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Проверка живости — её дёргает healthcheck в docker-compose."""
    return {"status": "ok", "env": settings.APP_ENV}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    """Корневой эндпоинт со ссылкой на документацию."""
    return {"service": settings.APP_NAME, "docs": "/docs"}
