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
    # Флаг аномалии (очередь ручной проверки): low_confidence / duplicate /
    # event_without_session / unknown_direction / possible_misread
    flag: str | None = None
    created_at: datetime


class DirectionAssign(BaseModel):
    """ТС-7: оператор вручную назначает направление событию UNKNOWN."""

    direction: str = Field(..., pattern="^(ENTRY|EXIT|entry|exit)$")


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
    paid_amount: float = 0.0
    # Старт сессии сдвигался на последнее событие серии дублей у шлагбаума
    entry_adjusted: bool = False
    # ТС-8: активная сессия старше порога — «зависла», нужен ручной разбор
    is_stale: bool = False
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


# --- Tariff ---
class TariffCreate(BaseModel):
    name: str = Field(..., max_length=255)
    free_minutes: int = Field(0, ge=0)
    price_per_hour: float = Field(..., ge=0)
    daily_cap: float | None = Field(None, ge=0)
    currency: str = Field("KZT", max_length=8)
    is_active: bool = True


class TariffUpdate(BaseModel):
    """Частичное обновление — все поля опциональны."""

    name: str | None = Field(None, max_length=255)
    free_minutes: int | None = Field(None, ge=0)
    price_per_hour: float | None = Field(None, ge=0)
    daily_cap: float | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=8)
    is_active: bool | None = None


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    free_minutes: int
    price_per_hour: float
    daily_cap: float | None
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Payment ---
class PaymentCreate(BaseModel):
    session_id: int


class PaymentWebhook(BaseModel):
    """Уведомление об оплате (в MVP — от Студии; у реального провайдера — подпись)."""

    provider_payment_id: str
    status: str = "paid"


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    amount: float
    currency: str
    status: str
    provider: str
    provider_payment_id: str
    provider_txn_id: str | None = None
    error_code: str | None = None
    pay_url: str | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BillingStatsOut(BaseModel):
    """Агрегации для карточек дашборда денег."""

    revenue_today: float
    unpaid_count: int
    avg_parked_seconds: int | None
