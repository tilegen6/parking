"""initial: camera + recognition_event

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camera",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "recognition_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plate_number", sa.String(length=32), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column("camera_name", sa.String(length=255), nullable=True),
        sa.Column("vehicle_photo_url", sa.Text(), nullable=True),
        sa.Column("plate_photo_url", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["camera.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recognition_event_plate_number", "recognition_event", ["plate_number"]
    )
    op.create_index(
        "ix_recognition_event_event_time", "recognition_event", ["event_time"]
    )
    op.create_index(
        "ix_recognition_event_camera_id", "recognition_event", ["camera_id"]
    )


def downgrade() -> None:
    op.drop_table("recognition_event")
    op.drop_table("camera")
