"""access_entry + alert + parking_session.access_type/free_until (итерация 3)

Revision ID: 0010_access_lists
Revises: 0009_user_audit
Create Date: 2026-07-17

Списки доступа (зел/жёлт/крас) на шлагбаум или глобально; оповещения по красному
списку; метка сессии о способе проезда (для расчёта оплаты при выезде).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_access_lists"
down_revision: str | None = "0009_user_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plate", sa.String(length=32), nullable=False),
        sa.Column("list_type", sa.String(length=16), nullable=False),
        sa.Column(
            "gate_id",
            sa.Integer(),
            sa.ForeignKey("gate.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_username", sa.String(length=64), nullable=True),
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
    op.create_index("ix_access_entry_plate", "access_entry", ["plate"])
    op.create_index("ix_access_entry_list_type", "access_entry", ["list_type"])
    op.create_index("ix_access_entry_gate_id", "access_entry", ["gate_id"])
    op.create_index("ix_access_entry_is_active", "access_entry", ["is_active"])

    op.create_table(
        "alert",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("plate", sa.String(length=32), nullable=True),
        sa.Column(
            "gate_id",
            sa.Integer(),
            sa.ForeignKey("gate.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_alert_kind", "alert", ["kind"])
    op.create_index("ix_alert_acknowledged", "alert", ["acknowledged"])
    op.create_index("ix_alert_created_at", "alert", ["created_at"])

    op.add_column(
        "parking_session",
        sa.Column("access_type", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "parking_session",
        sa.Column("free_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("parking_session", "free_until")
    op.drop_column("parking_session", "access_type")
    op.drop_index("ix_alert_created_at", "alert")
    op.drop_index("ix_alert_acknowledged", "alert")
    op.drop_index("ix_alert_kind", "alert")
    op.drop_table("alert")
    op.drop_index("ix_access_entry_is_active", "access_entry")
    op.drop_index("ix_access_entry_gate_id", "access_entry")
    op.drop_index("ix_access_entry_list_type", "access_entry")
    op.drop_index("ix_access_entry_plate", "access_entry")
    op.drop_table("access_entry")
