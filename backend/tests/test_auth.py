"""Тесты аутентификации: хеш пароля, JWT, логин, гварды ролей."""

from src.models import User, UserRole
from src.modules import auth


def _user(username="admin", role=UserRole.ADMIN, password="secret123", active=True):
    return User(
        username=username,
        password_hash=auth.hash_password(password),
        role=role,
        is_active=active,
    )


def test_hash_and_verify_password():
    h = auth.hash_password("hunter2")
    assert h != "hunter2"
    assert auth.verify_password("hunter2", h)
    assert not auth.verify_password("wrong", h)


def test_jwt_roundtrip():
    u = _user()
    u.id = 42
    token = auth.create_access_token(u)
    payload = auth.decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == UserRole.ADMIN
    assert payload["username"] == "admin"


async def _login(client, username, password):
    return await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


async def test_login_success_and_me(client, db):
    db.add(_user("admin", password="pass1234"))
    await db.commit()

    r = await _login(client, "admin", "pass1234")
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "admin"
    token = body["access_token"]

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["role"] == UserRole.ADMIN


async def test_login_wrong_password(client, db):
    db.add(_user("admin", password="right"))
    await db.commit()
    r = await _login(client, "admin", "wrong")
    assert r.status_code == 401


async def test_login_inactive_user(client, db):
    db.add(_user("ghost", password="pass1234", active=False))
    await db.commit()
    r = await _login(client, "ghost", "pass1234")
    assert r.status_code == 401


async def test_protected_requires_token(client):
    # без Authorization — 403 (нет credentials у HTTPBearer)
    r = await client.get("/api/v1/users")
    assert r.status_code in (401, 403)


async def test_invalid_token_rejected(client):
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert r.status_code == 401


async def test_role_guard_blocks_non_admin(client, db):
    db.add(_user("op", role=UserRole.OPERATOR, password="pass1234"))
    await db.commit()
    token = (await _login(client, "op", "pass1234")).json()["access_token"]
    r = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403  # оператор не админ
