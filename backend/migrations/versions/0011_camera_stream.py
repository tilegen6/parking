"""camera: доступ к RTSP-потоку, направление и признак жизни

Revision ID: 0011_camera_stream
Revises: 0010_access_lists
Create Date: 2026-07-22

Чтобы завести боевую Hikvision, в карточке камеры нужны логин/пароль/порт и путь
потока — из них бэкенд собирает RTSP-URL (пароль наружу не отдаём). direction
задаёт въезд/выезд для RTSP (в отличие от событий Hikvision, в потоке метаданных
направления нет). last_seen_at даёт честный статус online/offline.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_camera_stream"
down_revision: str | None = "0010_access_lists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("camera", sa.Column("direction", sa.String(length=16), nullable=True))
    op.add_column("camera", sa.Column("username", sa.String(length=64), nullable=True))
    op.add_column("camera", sa.Column("password", sa.String(length=255), nullable=True))
    op.add_column(
        "camera",
        sa.Column("rtsp_port", sa.Integer(), nullable=False, server_default="554"),
    )
    op.add_column(
        "camera", sa.Column("stream_path", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "camera", sa.Column("stream_url", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "camera",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("camera", "last_seen_at")
    op.drop_column("camera", "stream_url")
    op.drop_column("camera", "stream_path")
    op.drop_column("camera", "rtsp_port")
    op.drop_column("camera", "password")
    op.drop_column("camera", "username")
    op.drop_column("camera", "direction")
