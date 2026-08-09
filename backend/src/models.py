"""ORM-модели системы. Sprint 1: Camera и RecognitionEvent."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Direction:
    """Направление движения автомобиля относительно камеры."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    UNKNOWN = "UNKNOWN"


class CameraStatus:
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class Camera(Base):
    """Камера Hikvision, зарегистрированная в системе."""

    __tablename__ = "camera"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=CameraStatus.UNKNOWN)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    events: Mapped[list["RecognitionEvent"]] = relationship(
        back_populates="camera", cascade="all, delete-orphan"
    )


class RecognitionEvent(Base):
    """Событие распознавания номера (ANPR) от камеры Hikvision."""

    __tablename__ = "recognition_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    plate_number: Mapped[str | None] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(16), default=Direction.UNKNOWN)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now()
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Камера: связь по id (если найдена) + сырое имя/устройство из события
    camera_id: Mapped[int | None] = mapped_column(
        ForeignKey("camera.id", ondelete="SET NULL"), nullable=True, index=True
    )
    camera_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Фотографии (ссылки на объекты в MinIO)
    vehicle_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    plate_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Исходный payload события для отладки интеграции
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    camera: Mapped["Camera | None"] = relationship(back_populates="events")
