"""Тесты CRUD API тарифов (GET/POST/PUT/DELETE /api/v1/tariffs)."""

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.database import get_session
from src.modules import tariff as tariff_module


@pytest_asyncio.fixture
async def client(sessionmaker_):
    app = FastAPI()
    app.include_router(tariff_module.router)

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


def _tariff(**over):
    base = {
        "name": "Стандарт",
        "free_minutes": 15,
        "price_per_hour": 100,
        "daily_cap": 1000,
    }
    base.update(over)
    return base


async def test_create_returns_201_and_active(client):
    r = await client.post("/api/v1/tariffs", json=_tariff())
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Стандарт"
    assert body["free_minutes"] == 15
    assert body["is_active"] is True
    assert body["id"] > 0


async def test_list_returns_created(client):
    created = (await client.post("/api/v1/tariffs", json=_tariff())).json()
    r = await client.get("/api/v1/tariffs")
    assert r.status_code == 200
    assert any(t["id"] == created["id"] for t in r.json())


async def test_update_changes_fields(client):
    tid = (await client.post("/api/v1/tariffs", json=_tariff())).json()["id"]
    r = await client.put(f"/api/v1/tariffs/{tid}", json={"price_per_hour": 80})
    assert r.status_code == 200
    assert r.json()["price_per_hour"] == 80
    assert r.json()["free_minutes"] == 15  # остальное без изменений


async def test_delete_then_404(client):
    tid = (await client.post("/api/v1/tariffs", json=_tariff())).json()["id"]
    r = await client.delete(f"/api/v1/tariffs/{tid}")
    assert r.status_code == 204
    assert (await client.get(f"/api/v1/tariffs/{tid}")).status_code == 404


async def test_get_missing_returns_404(client):
    assert (await client.get("/api/v1/tariffs/9999")).status_code == 404


async def test_update_missing_returns_404(client):
    r = await client.put("/api/v1/tariffs/9999", json={"price_per_hour": 50})
    assert r.status_code == 404
