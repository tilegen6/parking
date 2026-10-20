"""Общие фикстуры тестов: in-memory SQLite + изолированное FastAPI-приложение.

Используется StaticPool — единое соединение, чтобы in-memory БД была общей
для сидинга и для запросов через клиент.
"""

import os

# Секреты обязательны для Settings — задаём до импорта src.config
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("MINIO_ROOT_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-signing-key-at-least-32-bytes")

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database import Base, get_session
from src.models import User, UserRole
from src.modules import access as access_module
from src.modules import auth as auth_module
from src.modules import camera as camera_module
from src.modules import gate as gate_module
from src.modules import recognition as recognition_module
from src.modules import session as session_module
from src.modules import user as user_module


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker_(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(sessionmaker_):
    """Сессия для прямого сидинга/проверок в БД."""
    async with sessionmaker_() as s:
        yield s


@pytest_asyncio.fixture
async def operator_headers(db):
    user = User(
        username="session-operator",
        role=UserRole.OPERATOR,
        password_hash="unused-token-fixture",
    )
    db.add(user)
    await db.commit()
    return {"Authorization": "Bearer " + auth_module.create_access_token(user)}


@pytest_asyncio.fixture
async def client(sessionmaker_):
    """HTTP-клиент к минимальному приложению (роутеры сессий и распознавания)."""
    app = FastAPI()
    app.include_router(session_module.router)
    app.include_router(recognition_module.router)
    app.include_router(gate_module.router)
    app.include_router(camera_module.router)
    app.include_router(auth_module.router)
    app.include_router(user_module.router)
    app.include_router(access_module.router)

    async def _override_get_session():
        async with sessionmaker_() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
