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
