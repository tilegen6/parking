"""kaspi payment fields: provider_txn_id, error_code + uniq (provider, ref)

Revision ID: 0006_kaspi_payment_fields
Revises: 0005_paid_amount
Create Date: 2026-07-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_kaspi_payment_fields"
down_revision: str | None = "0005_paid_amount"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment",
        sa.Column("provider_txn_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "payment",
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )
    # Идемпотентность оплаты: не более одной записи на (провайдер, id у провайдера)
    op.create_unique_constraint(
        "uq_payment_provider_ref",
        "payment",
        ["provider", "provider_payment_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_payment_provider_ref", "payment", type_="unique")
    op.drop_column("payment", "error_code")
    op.drop_column("payment", "provider_txn_id")
