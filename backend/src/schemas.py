"""Pydantic-схемы (валидация запросов и сериализация ответов)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Camera ---
class CameraCreate(BaseModel):
    name: str = Field(..., max_length=255)
    ip_address: str | None = Field(None, max_length=64)
    type: str | None = Field(None, max_length=64)
    location: str | None = Field(None, max_length=255)
    status: str = "unknown"


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip_address: str | None
    type: str | None
    location: str | None
    status: str
    created_at: datetime


# --- RecognitionEvent ---
class RecognitionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_number: str | None
    direction: str
    event_time: datetime
    confidence: float | None
    camera_id: int | None
    camera_name: str | None
    vehicle_photo_url: str | None
    plate_photo_url: str | None
    created_at: datetime


class PaginatedEvents(BaseModel):
    """Постраничный ответ для таблицы событий на фронтенде."""

    items: list[RecognitionEventOut]
    total: int
    page: int
    limit: int
    pages: int


# --- ParkingSession ---
class ParkingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_number: str
    status: str
    entry_time: datetime
    exit_time: datetime | None
    last_seen: datetime | None
    duration_seconds: int | None
    # Вычисляемое: для active = «сейчас минус въезд», для закрытой = duration_seconds
    parked_seconds: int | None = None
    price: float | None
    entry_event_id: int | None
    exit_event_id: int | None
    entry_camera_id: int | None
    exit_camera_id: int | None
    created_at: datetime
    updated_at: datetime


class PaginatedSessions(BaseModel):
    """Постраничный ответ для таблицы парковочных сессий."""

    items: list[ParkingSessionOut]
    total: int
    page: int
    limit: int
    pages: int
