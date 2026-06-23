"""parking_session + recognition_event.flag

Revision ID: 0002_parking_session
Revises: 0001_initial
Create Date: 2026-06-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_parking_session"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Флаг аномалий на событии распознавания (low_confidence / event_without_session)
    op.add_column(
        "recognition_event",
        sa.Column("flag", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_recognition_event_flag", "recognition_event", ["flag"])

    op.create_table(
        "parking_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plate_number", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("entry_event_id", sa.Integer(), nullable=True),
        sa.Column("exit_event_id", sa.Integer(), nullable=True),
        sa.Column("entry_camera_id", sa.Integer(), nullable=True),
        sa.Column("exit_camera_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["entry_event_id"], ["recognition_event.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["exit_event_id"], ["recognition_event.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["entry_camera_id"], ["camera.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["exit_camera_id"], ["camera.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_parking_session_plate_number", "parking_session", ["plate_number"]
    )
    op.create_index("ix_parking_session_status", "parking_session", ["status"])
    op.create_index("ix_parking_session_entry_time", "parking_session", ["entry_time"])
    # Составной индекс под самый частый запрос: активная сессия по номеру
    op.create_index(
        "ix_parking_session_plate_status",
        "parking_session",
        ["plate_number", "status"],
    )


def downgrade() -> None:
    op.drop_table("parking_session")
    op.drop_index("ix_recognition_event_flag", table_name="recognition_event")
    op.drop_column("recognition_event", "flag")
