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
