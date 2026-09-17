"""Одна активная сессия на (номер, шлагбаум): схлопнуть дубли + уникальный индекс

Revision ID: 0013_active_session_unique
Revises: 0012_plate_canon
Create Date: 2026-07-22

Пачка ENTRY-событий Hikvision на один проезд под конкуренцией плодила несколько
активных сессий на один номер. Защита — частичный уникальный индекс. Перед его
созданием схлопываем уже накопленные дубли: оставляем самую раннюю активную,
остальные → auto_closed (на ручную проверку), иначе CREATE INDEX упадёт.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_active_session_unique"
down_revision: str | None = "0012_plate_canon"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    # Схлопнуть дубли: из группы (plate_number, coalesce(gate_id,-1)) активных
    # оставить одну (минимальный id — самый ранний въезд), прочие → auto_closed.
    conn.execute(
        sa.text(
            """
            UPDATE parking_session
               SET status = 'auto_closed'
             WHERE status = 'active'
               AND id NOT IN (
                   SELECT MIN(id)
                     FROM parking_session
                    WHERE status = 'active'
                    GROUP BY plate_number, COALESCE(gate_id, -1)
               )
            """
        )
    )
    op.create_index(
        "uq_active_session_plate_gate",
        "parking_session",
        ["plate_number", sa.text("COALESCE(gate_id, -1)")],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_session_plate_gate", table_name="parking_session")
