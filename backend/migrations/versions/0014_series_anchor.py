"""parking_session.series_started_at — неизменяемый якорь окна сдвига старта

Revision ID: 0014_series_anchor
Revises: 0013_active_session_unique
Create Date: 2026-07-22

Окно сдвига старта сессии считалось от last_seen, поэтому машина, которую камера
видит раз в <window, обнуляла счётчик бесконечно. Якорь = первое событие серии,
окно считается от него. Существующим сессиям якорь = entry_time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_series_anchor"
down_revision: str | None = "0013_active_session_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parking_session",
        sa.Column("series_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Для уже существующих сессий якорь = момент въезда (сдвигов ещё не было).
    op.execute(
        "UPDATE parking_session SET series_started_at = entry_time "
        "WHERE series_started_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("parking_session", "series_started_at")
