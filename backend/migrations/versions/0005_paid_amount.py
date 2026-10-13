"""parking_session.paid_amount

Revision ID: 0005_paid_amount
Revises: 0004_payment
Create Date: 2026-07-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_paid_amount"
down_revision: str | None = "0004_payment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parking_session",
        sa.Column("paid_amount", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("parking_session", "paid_amount")
