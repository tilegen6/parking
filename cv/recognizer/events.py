"""Сборка события распознавания в вендор-нейтральном контракте CV->backend.

Контракт: cv/contract/recognition-event.schema.json. `to_contract()` отдаёт
ровно поля схемы (без лишних ключей), `to_backend_json()` — форму, которую
принимает существующий `POST /api/v1/hikvision/anpr-event`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

SOURCE = "own-cv-v1"


class Direction(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    UNKNOWN = "UNKNOWN"


def normalize_direction(value: str | Direction | None) -> Direction:
    if isinstance(value, Direction):
        return value
    v = (value or "").strip().lower()
    if v in {"entry", "enter", "in", "forward"}:
        return Direction.ENTRY
    if v in {"exit", "leave", "out", "reverse"}:
        return Direction.EXIT
    return Direction.UNKNOWN


def _iso(dt: datetime) -> str:
    """ISO 8601 со смещением TZ; наивное время трактуем как UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@dataclass(frozen=True)
class RecognitionEvent:
    plate_number: str | None
    direction: Direction
    event_time: datetime
    confidence: float | None = None
    camera_name: str | None = None
    source: str = SOURCE
    plate_photo: str | None = None
    vehicle_photo: str | None = None
    raw_ref: str | None = None
    plate_raw: str | None = None
    normalization_status: str | None = None

    def to_contract(self) -> dict:
        """Чистая форма контракта (валидна по recognition-event.schema.json)."""
        result = {
            "plate_number": self.plate_number,
            "direction": self.direction.value,
            "event_time": _iso(self.event_time),
            "confidence": self.confidence,
            "camera_name": self.camera_name,
            "source": self.source,
            "photos": {"plate": self.plate_photo, "vehicle": self.vehicle_photo},
            "raw_ref": self.raw_ref,
        }
        if self.plate_raw is not None:
            result["plate_raw"] = self.plate_raw
        if self.normalization_status is not None:
            result["normalization_status"] = self.normalization_status
        return result

    def to_backend_json(self) -> dict:
        """Форма для POST /api/v1/hikvision/anpr-event (hikvision.parse_json)."""
        result = {
            "plateNumber": self.plate_number,
            "direction": self.direction.value,
            "confidence": self.confidence,
            "dateTime": _iso(self.event_time),
            "channelName": self.camera_name,
            "source": self.source,
        }
        if self.plate_raw is not None:
            result["plateRaw"] = self.plate_raw
        if self.normalization_status is not None:
            result["normalizationStatus"] = self.normalization_status
        return result


def build_event(
    plate_number: str | None,
    direction: str | Direction | None,
    *,
    confidence: float | None = None,
    camera_name: str | None = None,
    event_time: datetime | None = None,
    plate_photo: str | None = None,
    vehicle_photo: str | None = None,
    raw_ref: str | None = None,
    plate_raw: str | None = None,
    normalization_status: str | None = None,
) -> RecognitionEvent:
    return RecognitionEvent(
        plate_number=plate_number or None,
        direction=normalize_direction(direction),
        event_time=event_time or datetime.now(timezone.utc),
        confidence=confidence,
        camera_name=camera_name,
        plate_photo=plate_photo,
        vehicle_photo=vehicle_photo,
        raw_ref=raw_ref,
        plate_raw=plate_raw,
        normalization_status=normalization_status,
    )
