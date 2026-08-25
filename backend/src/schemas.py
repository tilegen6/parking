"""Pydantic-схемы (валидация запросов и сериализация ответов)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Auth / Users ---
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)
    full_name: str | None = Field(None, max_length=255)
    role: str = "operator"
    is_active: bool = True


class UserUpdate(BaseModel):
    """Частичное обновление; password задаётся только при смене."""

    password: str | None = Field(None, min_length=4, max_length=128)
    full_name: str | None = Field(None, max_length=255)
    role: str | None = None
    is_active: bool | None = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    username: str | None
    action: str
    entity: str | None
    entity_id: str | None
    detail: str | None
    created_at: datetime


# --- Access lists (зелёный/жёлтый/красный) ---
class AccessEntryCreate(BaseModel):
    plate: str = Field(..., min_length=1, max_length=32)
    list_type: str  # green | yellow | red
    gate_id: int | None = None  # None = на все шлагбаумы
    valid_until: datetime | None = None  # жёлтый: бесплатно до этого момента
    note: str | None = Field(None, max_length=255)
    is_active: bool = True


class AccessEntryUpdate(BaseModel):
    list_type: str | None = None
    gate_id: int | None = None
    valid_until: datetime | None = None
    note: str | None = Field(None, max_length=255)
    is_active: bool | None = None


class AccessEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate: str
    list_type: str
    gate_id: int | None
    valid_until: datetime | None
    note: str | None
    is_active: bool
    created_by_username: str | None
    created_at: datetime
    updated_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    plate: str | None
    gate_id: int | None
    message: str | None
    acknowledged: bool
    created_at: datetime


# --- Gate (шлагбаум/зона) ---
class GateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    zone: str | None = Field(None, max_length=255)
    level: int = Field(1, ge=1)
    is_active: bool = True


class GateUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    zone: str | None = Field(None, max_length=255)
    level: int | None = Field(None, ge=1)
    is_active: bool | None = None


class GateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    zone: str | None
    level: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Camera ---
class CameraBase(BaseModel):
    """Общие поля карточки камеры (включая доступ к потоку)."""

    ip_address: str | None = Field(None, max_length=64)
    type: str | None = Field(None, max_length=64)
    location: str | None = Field(None, max_length=255)
    gate_id: int | None = None
    direction: Literal["entry", "exit"] | None = None
    username: str | None = Field(None, max_length=64)
    # Пароль принимаем, но никогда не отдаём обратно (см. CameraOut).
    password: str | None = Field(None, max_length=255)
    stream_path: str | None = Field(None, max_length=255)
    stream_url: str | None = Field(None, max_length=512)


class CameraCreate(CameraBase):
    name: str = Field(..., max_length=255)
    status: str = "unknown"
    rtsp_port: int = Field(554, ge=1, le=65535)


class CameraUpdate(CameraBase):
    """Частичное обновление камеры (в т.ч. привязка к шлагбауму)."""

    name: str | None = Field(None, max_length=255)
    status: str | None = None
    # None = «поле не прислали», порт остаётся прежним (см. exclude_unset).
    rtsp_port: int | None = Field(None, ge=1, le=65535)


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip_address: str | None
    type: str | None
    location: str | None
    status: str
    gate_id: int | None = None
    direction: str | None = None
    username: str | None = None
    rtsp_port: int = 554
    stream_path: str | None = None
    stream_url: str | None = None
    last_seen_at: datetime | None = None
    created_at: datetime
    # Пароль наружу не уходит — только признак, что он задан, и готовый URL с
    # замаскированным паролем (чтобы оператор видел, куда именно подключаемся).
    has_password: bool = False
    stream_url_display: str | None = None


class CameraCheckResult(BaseModel):
    """Результат проверки связи с камерой (TCP-пробы порта RTSP)."""

    camera_id: int
    reachable: bool
    status: str
    target: str | None = None
    detail: str | None = None


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
    # Шлагбаум/зона сессии (None = не привязана)
    gate_id: int | None = None
    # Способ проезда по спискам: green/yellow/None (обычная платная)
    access_type: str | None = None
    free_until: datetime | None = None
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
