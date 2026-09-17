"""parking_session.entry_adjusted — старт сессии сдвигался по дублям у шлагбаума

Revision ID: 0007_entry_adjusted
Revises: 0006_kaspi_payment_fields
Create Date: 2026-07-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_entry_adjusted"
down_revision: str | None = "0006_kaspi_payment_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parking_session",
        sa.Column(
            "entry_adjusted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("parking_session", "entry_adjusted")
