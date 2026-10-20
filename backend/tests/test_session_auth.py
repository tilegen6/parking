"""Session data and manual changes use real JWT/DB-user checks."""

from datetime import datetime, timezone

import pytest

from src.models import ParkingSession, User, UserRole
from src.modules.auth import create_access_token


@pytest.mark.parametrize("path", ["", "/active", "/unpaid", "/1"])
async def test_session_reads_require_authentication(client, path):
    response = await client.get("/api/v1/parking-sessions" + path)
    assert response.status_code == 401


async def test_invalid_session_token(client):
    response = await client.get(
        "/api/v1/parking-sessions", headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("role", UserRole.ALL)
async def test_active_users_can_read_sessions(client, db, role):
    user = User(username="reader", role=role, password_hash="not-used")
    db.add(user)
    await db.commit()
    response = await client.get(
        "/api/v1/parking-sessions",
        headers={"Authorization": "Bearer " + create_access_token(user)},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_disabled_session_user_is_rejected(client, db):
    user = User(
        username="disabled",
        role=UserRole.OPERATOR,
        password_hash="not-used",
        is_active=False,
    )
    db.add(user)
    await db.commit()
    response = await client.get(
        "/api/v1/parking-sessions",
        headers={"Authorization": "Bearer " + create_access_token(user)},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "role,expected",
    [(UserRole.ADMIN, 200), (UserRole.OPERATOR, 200), (UserRole.LIST_MANAGER, 403)],
)
async def test_session_cancel_requires_operational_role(client, db, role, expected):
    user = User(username="actor", role=role, password_hash="not-used")
    parking = ParkingSession(
        plate_number="123ABC02", entry_time=datetime.now(timezone.utc)
    )
    db.add_all([user, parking])
    await db.commit()
    response = await client.post(
        f"/api/v1/parking-sessions/{parking.id}/cancel",
        headers={"Authorization": "Bearer " + create_access_token(user)},
    )
    assert response.status_code == expected


@pytest.mark.parametrize("path", ["/recognition/events", "/recognition/events/1"])
async def test_recognition_journal_also_requires_authentication(client, path):
    assert (await client.get("/api/v1" + path)).status_code == 401
