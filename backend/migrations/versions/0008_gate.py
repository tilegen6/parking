"""gate (шлагбаумы/зоны) + camera.gate_id + parking_session.gate_id

Revision ID: 0008_gate
Revises: 0007_entry_adjusted
Create Date: 2026-07-17

Итерация 1 «Шлагбаумы/зоны»: раздельный учёт по шлагбаумам, фундамент под
списки доступа и шлагбаум 2-го уровня. Сеем один дефолтный шлагбаум, но
существующие камеры/сессии НЕ привязываем (остаются NULL) — админ распределит.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_gate"
down_revision: str | None = "0007_entry_adjusted"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("zone", sa.String(length=255), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_gate_is_active", "gate", ["is_active"])

    # Дефолтный шлагбаум, чтобы было к чему привязывать камеры
    op.execute(
        "INSERT INTO gate (name, zone, level, is_active) "
        "VALUES ('Шлагбаум №1', 'Двор', 1, true)"
    )

    op.add_column(
        "camera",
        sa.Column(
            "gate_id",
            sa.Integer(),
            sa.ForeignKey("gate.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_camera_gate_id", "camera", ["gate_id"])

    op.add_column(
        "parking_session",
        sa.Column(
            "gate_id",
            sa.Integer(),
            sa.ForeignKey("gate.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_parking_session_gate_id", "parking_session", ["gate_id"])


def downgrade() -> None:
    op.drop_index("ix_parking_session_gate_id", "parking_session")
    op.drop_column("parking_session", "gate_id")
    op.drop_index("ix_camera_gate_id", "camera")
    op.drop_column("camera", "gate_id")
    op.drop_index("ix_gate_is_active", "gate")
    op.drop_table("gate")
