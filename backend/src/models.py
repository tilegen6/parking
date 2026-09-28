"""ORM-модели системы. Sprint 1: Camera и RecognitionEvent."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class UserRole:
    """Роли пользователей админки (списки ведут пользователи с правами, ТС-2/3/4)."""

    ADMIN = "admin"  # всё + управление пользователями
    OPERATOR = "operator"  # диспетчер: ручные действия по сессиям/событиям
    LIST_MANAGER = "list_manager"  # ведение списков доступа (зел/жёлт/крас)

    ALL = (ADMIN, OPERATOR, LIST_MANAGER)


class User(Base):
    """Пользователь админки. Аудит действий опирается на его личность."""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.OPERATOR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    """Журнал действий пользователей — кто/что/когда (привязка к личности)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)  # напр. user.create
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Direction:
    """Направление движения автомобиля относительно камеры."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    UNKNOWN = "UNKNOWN"


class CameraStatus:
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class SessionStatus:
    """Статусы парковочной сессии (ТЗ §4.2)."""

    ACTIVE = "active"  # на парковке, оплата не получена
    PAID = "paid"  # оплачено, выезд разрешён (v2)
    UNPAID = "unpaid"  # выехал без оплаты (в MVP v1 — обычный выезд)
    CANCELLED = "cancelled"  # отменена вручную админом
    WHITELIST = "whitelist"  # бесплатный въезд по белому списку (v2)
    # ТС-3: новый въезд при зависшей активной (пропущенный выезд) — старую
    # закрываем этим статусом и выводим на ручную проверку
    AUTO_CLOSED = "auto_closed"


class EventFlag:
    """Флаги аномальных событий распознавания (ТЗ §6.2) — очередь ручной проверки."""

    LOW_CONFIDENCE = "low_confidence"  # confidence < порога / номер не распознан
    EVENT_WITHOUT_SESSION = "event_without_session"  # выезд без активной сессии
    DUPLICATE = "duplicate"  # ТС-2: повторное событие того же номера
    UNKNOWN_DIRECTION = "unknown_direction"  # ТС-7: направление не определено
    POSSIBLE_MISREAD = "possible_misread"  # ТС-9: похож на активный номер (±1 символ)
    ACCESS_DENIED_RED = "access_denied_red"  # красный список — не пустили


class AccessListType:
    """Списки доступа (по шлагбауму или глобально)."""

    GREEN = "green"  # всегда пускать, без оплаты
    YELLOW = "yellow"  # без оплаты до valid_until, далее по тарифу
    RED = "red"  # не пускать + сигнал ответственному
    ALL = (GREEN, YELLOW, RED)


class AccessType:
    """Как проехала машина (метка сессии) — определяет оплату при выезде."""

    GREEN = "green"  # бесплатно
    YELLOW = "yellow"  # бесплатно до free_until, далее тариф
    PAID = "paid"  # обычная платная («остальные»)


class AlertKind:
    """Тип оповещения ответственному."""

    RED_LIST = "red_list"  # подъехала машина из красного списка


class Gate(Base):
    """Шлагбаум/КПП с зоной. Списки доступа и учёт — на каждый шлагбаум свои.

    level: 1 — внешний КПП (двор), 2 — внутренний (напр. парковка отеля).
    Камеры и сессии привязываются к шлагбауму → раздельный учёт по зонам.
    """

    __tablename__ = "gate"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    zone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AccessEntry(Base):
    """Запись списка доступа: номер → тип списка на шлагбауме (или глобально).

    gate_id=None → действует на все шлагбаумы. valid_until — для жёлтого списка
    момент, до которого бесплатно. created_by/username — кто добавил (аудит).
    """

    __tablename__ = "access_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    plate: Mapped[str] = mapped_column(String(32), index=True)  # нормализованный
    list_type: Mapped[str] = mapped_column(String(16), index=True)
    gate_id: Mapped[int | None] = mapped_column(
        ForeignKey("gate.id", ondelete="CASCADE"), nullable=True, index=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    created_by_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Alert(Base):
    """Оповещение ответственному (напр. подъехала машина из красного списка)."""

    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    plate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gate_id: Mapped[int | None] = mapped_column(
        ForeignKey("gate.id", ondelete="SET NULL"), nullable=True
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Camera(Base):
    """Камера Hikvision, зарегистрированная в системе."""

    __tablename__ = "camera"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=CameraStatus.UNKNOWN)
    # К какому шлагбауму относится камера (её события → сессии этого шлагбаума)
    gate_id: Mapped[int | None] = mapped_column(
        ForeignKey("gate.id", ondelete="SET NULL"), nullable=True, index=True
    )
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

    # Флаг аномалии (low_confidence / event_without_session) — для разбора в admin
    flag: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    camera: Mapped["Camera | None"] = relationship(back_populates="events")


class ParkingSession(Base):
    """Парковочная сессия: агрегат событий въезда и выезда одного авто."""

    __tablename__ = "parking_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    plate_number: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=SessionStatus.ACTIVE, index=True
    )

    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    exit_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Последнее «замеченное» событие — обновляется дублями (ТЗ §6.2)
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(nullable=True)

    # Стоимость (последняя посчитанная) + сколько уже оплачено (доплаты/шлагбаум)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0)

    # Машина стояла перед шлагбаумом и распознавалась несколько раз: старт
    # сессии сдвинут на ПОСЛЕДНЕЕ событие серии (решение клиента). Пометка
    # остаётся для разборов — полная история в recognition_event.
    entry_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Шлагбаум/зона сессии (из камеры события). None = не привязан к шлагбауму.
    gate_id: Mapped[int | None] = mapped_column(
        ForeignKey("gate.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Как проехала машина по спискам: green (бесплатно) / yellow (бесплатно до
    # free_until) / None = обычная платная. Влияет на расчёт при выезде.
    access_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    free_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Связи с событиями распознавания (въезд/выезд)
    entry_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("recognition_event.id", ondelete="SET NULL"), nullable=True
    )
    exit_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("recognition_event.id", ondelete="SET NULL"), nullable=True
    )
    entry_camera_id: Mapped[int | None] = mapped_column(
        ForeignKey("camera.id", ondelete="SET NULL"), nullable=True
    )
    exit_camera_id: Mapped[int | None] = mapped_column(
        ForeignKey("camera.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Tariff(Base):
    """Тариф парковки (ТЗ §3.4): правила расчёта стоимости по времени.

    parking_lot_id из ТЗ пока опущен — таблицы парковок ещё нет (один объект).
    Активный тариф (is_active) используется для расчёта стоимости сессии.
    """

    __tablename__ = "tariff"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    free_minutes: Mapped[int] = mapped_column(default=0)  # бесплатный период
    price_per_hour: Mapped[float] = mapped_column(Float)
    daily_cap: Mapped[float | None] = mapped_column(Float, nullable=True)  # /сутки
    currency: Mapped[str] = mapped_column(String(8), default="KZT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaymentStatus:
    """Статусы платежа."""

    PENDING = "pending"  # создан, ждём подтверждения от провайдера
    PAID = "paid"  # оплачено
    FAILED = "failed"  # отклонён / ошибка


class Payment(Base):
    """Платёж за парковочную сессию через провайдера (в MVP — mock)."""

    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("parking_session.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="KZT")
    status: Mapped[str] = mapped_column(
        String(16), default=PaymentStatus.PENDING, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    # id платежа у провайдера — по нему приходит webhook / идемпотентность.
    # Для Kaspi онлайн — txn_id запроса; для autopay — requestId.
    provider_payment_id: Mapped[str] = mapped_column(String(64), index=True)
    # Номер оплаты в системе провайдера (Kaspi transactionId / prv_txn), если есть
    provider_txn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Код ошибки провайдера для неуспешных попыток (напр. INSUFFICIENT_FUNDS)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pay_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Один успешный платёж на (провайдер, id платежа у провайдера): защита от
    # двойного списания при повторном webhook/pay с тем же txn_id (Протокол §7).
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_payment_id", name="uq_payment_provider_ref"
        ),
    )
