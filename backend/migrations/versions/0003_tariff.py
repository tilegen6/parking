"""tariff

Revision ID: 0003_tariff
Revises: 0002_parking_session
Create Date: 2026-07-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tariff"
down_revision: str | None = "0002_parking_session"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tariff",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("free_minutes", sa.Integer(), nullable=False),
        sa.Column("price_per_hour", sa.Float(), nullable=False),
        sa.Column("daily_cap", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tariff_is_active", "tariff", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_tariff_is_active", table_name="tariff")
    op.drop_table("tariff")
