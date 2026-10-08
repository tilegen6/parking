"""Тесты управления пользователями (admin) + аудит."""

import pytest_asyncio

from src.models import User, UserRole
from src.modules import auth


@pytest_asyncio.fixture
async def admin_token(client, db):
    db.add(
        User(
            username="root",
            password_hash=auth.hash_password("rootpass"),
            role=UserRole.ADMIN,
        )
    )
    await db.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "rootpass"}
    )
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def test_create_list_update_user_with_audit(client, admin_token):
    # создать
    r = await client.post(
        "/api/v1/users",
        headers=_h(admin_token),
        json={
            "username": "operator1",
            "password": "op12345",
            "full_name": "Оператор Один",
            "role": "operator",
        },
    )
    assert r.status_code == 201
    uid = r.json()["id"]
    assert "password" not in r.json()  # хеш наружу не отдаём

    # новый оператор может залогиниться
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "operator1", "password": "op12345"},
    )
    assert login.status_code == 200

    # список
    r = await client.get("/api/v1/users", headers=_h(admin_token))
    assert any(u["username"] == "operator1" for u in r.json())

    # обновить роль
    r = await client.put(
        f"/api/v1/users/{uid}",
        headers=_h(admin_token),
        json={"role": "list_manager"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "list_manager"

    # аудит зафиксировал create + update с привязкой к root
    audit = await client.get("/api/v1/audit-log", headers=_h(admin_token))
    actions = [(a["action"], a["username"]) for a in audit.json()]
    assert ("user.create", "root") in actions
    assert ("user.update", "root") in actions


async def test_duplicate_username_conflict(client, admin_token):
    body = {"username": "dup", "password": "pass1234", "role": "operator"}
    r1 = await client.post("/api/v1/users", headers=_h(admin_token), json=body)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/users", headers=_h(admin_token), json=body)
    assert r2.status_code == 409


async def test_bad_role_rejected(client, admin_token):
    r = await client.post(
        "/api/v1/users",
        headers=_h(admin_token),
        json={"username": "baduser", "password": "pass1234", "role": "superadmin"},
    )
    assert r.status_code == 400


async def test_cannot_disable_self(client, admin_token, db):
    me = (await client.get("/api/v1/auth/me", headers=_h(admin_token))).json()
    r = await client.put(
        f"/api/v1/users/{me['id']}",
        headers=_h(admin_token),
        json={"is_active": False},
    )
    assert r.status_code == 400


async def test_non_admin_cannot_manage_users(client, db):
    db.add(
        User(
            username="op",
            password_hash=auth.hash_password("op12345"),
            role=UserRole.OPERATOR,
        )
    )
    await db.commit()
    token = (
        await client.post(
            "/api/v1/auth/login", json={"username": "op", "password": "op12345"}
        )
    ).json()["access_token"]
    r = await client.post(
        "/api/v1/users",
        headers=_h(token),
        json={"username": "newbie", "password": "pass1234", "role": "operator"},
    )
    assert r.status_code == 403
