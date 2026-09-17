"""Только один активный тариф: погасить лишние + уникальный индекс

Revision ID: 0015_tariff_single_active
Revises: 0014_series_anchor
Create Date: 2026-07-22

Одновременно активных тарифов может быть несколько: бэкенд брал последний по id,
фронт — первый, показанная сумма расходилась с выставленной. Оставляем активным
самый свежий (максимальный id), остальные гасим, дальше держим индексом.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_tariff_single_active"
down_revision: str | None = "0014_series_anchor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Гасим все активные, кроме самого свежего (его и брал бэкенд — поведение
    # не меняется, просто фиксируется).
    op.execute(
        """
        UPDATE tariff
           SET is_active = false
         WHERE is_active
           AND id <> (SELECT MAX(id) FROM tariff WHERE is_active)
        """
    )
    op.create_index(
        "uq_tariff_single_active",
        "tariff",
        [sa.text("COALESCE(is_active, false)")],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_tariff_single_active", table_name="tariff")
