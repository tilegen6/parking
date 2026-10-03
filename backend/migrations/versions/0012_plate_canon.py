"""Канонизация номера: recognition_event.plate_raw + бэкфилл нормализации

Revision ID: 0012_plate_canon
Revises: 0011_camera_stream
Create Date: 2026-07-22

Номер теперь канонизируется на приёме (верхний регистр, латиница, только
буквы/цифры) и по нему идут ВСЕ сравнения. Сырой текст события сохраняем в
recognition_event.plate_raw. Существующие строки приводим к канону, чтобы
старые сессии продолжали находиться (пробелы/регистр/кириллица).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_plate_canon"
down_revision: str | None = "0011_camera_stream"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Кириллические гомоглифы → латиница (тот же map, что в access.normalize_plate).
_CYR = {
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "У": "Y",
    "Х": "X",
}


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    upper = value.upper()
    for cyr, lat in _CYR.items():
        upper = upper.replace(cyr, lat)
    canon = "".join(ch for ch in upper if ch.isascii() and ch.isalnum())
    return canon or None


def upgrade() -> None:
    op.add_column(
        "recognition_event",
        sa.Column("plate_raw", sa.String(length=64), nullable=True),
    )

    # Бэкфилл: сырой текст в plate_raw, plate_number — к канону.
    conn = op.get_bind()
    ev = sa.table(
        "recognition_event",
        sa.column("id", sa.Integer),
        sa.column("plate_number", sa.String),
        sa.column("plate_raw", sa.String),
    )
    for row in conn.execute(sa.select(ev.c.id, ev.c.plate_number)):
        raw = row.plate_number
        conn.execute(
            ev.update()
            .where(ev.c.id == row.id)
            .values(plate_raw=raw, plate_number=_normalize(raw))
        )

    ps = sa.table(
        "parking_session",
        sa.column("id", sa.Integer),
        sa.column("plate_number", sa.String),
    )
    for row in conn.execute(sa.select(ps.c.id, ps.c.plate_number)):
        canon = _normalize(row.plate_number)
        if canon and canon != row.plate_number:
            conn.execute(
                ps.update().where(ps.c.id == row.id).values(plate_number=canon)
            )


def downgrade() -> None:
    # plate_number обратно к сырому не восстанавливаем (данные утеряны при
    # канонизации), только снимаем добавленную колонку.
    op.drop_column("recognition_event", "plate_raw")
