"""Парсинг ANPR-событий камеры Hikvision.

Камера присылает событие одним из способов:
  * multipart/form-data — XML-часть (EventNotificationAlert) + картинки;
  * application/xml или text/xml — только XML;
  * application/json — JSON (некоторые прошивки / прокси).

Здесь мы приводим всё к единому словарю ParsedEvent.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


@dataclass
class ParsedEvent:
    plate_number: str | None = None
    direction: str = "UNKNOWN"
    event_time: datetime | None = None
    confidence: float | None = None
    camera_name: str | None = None
    raw_payload: str | None = None
    # имя_объекта -> (bytes, content_type)
    photos: dict[str, tuple[bytes, str]] = field(default_factory=dict)


def _strip_ns(tag: str) -> str:
    """Убрать XML namespace: '{http://...}licensePlate' -> 'licensePlate'."""
    return tag.split("}", 1)[-1]


def _find_first(root: ET.Element, *names: str) -> str | None:
    """Найти текст первого элемента с любым из имён (без учёта namespace)."""
    wanted = {n.lower() for n in names}
    for el in root.iter():
        if _strip_ns(el.tag).lower() in wanted and el.text and el.text.strip():
            return el.text.strip()
    return None


def _normalize_direction(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    v = value.strip().lower()
    if v in {"forward", "in", "entry", "enter"}:
        return "ENTRY"
    if v in {"reverse", "out", "exit", "leave"}:
        return "EXIT"
    return "UNKNOWN"


def _parse_time(value: str | None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Не удалось разобрать время события: %s", value)
    return datetime.now(timezone.utc)


def parse_xml(payload: bytes | str) -> ParsedEvent:
    """Разобрать XML-событие EventNotificationAlert."""
    raw = (
        payload.decode("utf-8", errors="replace")
        if isinstance(payload, bytes)
        else payload
    )
    event = ParsedEvent(raw_payload=raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        logger.error("Битый XML от камеры: %s", exc)
        return event

    event.plate_number = _find_first(root, "licensePlate", "plateNumber", "plate")
    event.direction = _normalize_direction(
        _find_first(root, "direction", "vehicleDirection")
    )
    event.event_time = _parse_time(_find_first(root, "dateTime", "captureTime", "time"))
    event.camera_name = _find_first(
        root, "channelName", "deviceName", "cameraName", "ipAddress"
    )

    conf = _find_first(root, "confidenceLevel", "confidence")
    if conf:
        try:
            value = float(conf)
            # Hikvision обычно отдаёт 0..100, фронту удобнее 0..1
            event.confidence = value / 100 if value > 1 else value
        except ValueError:
            pass

    return event


def parse_json(data: dict) -> ParsedEvent:
    """Разобрать JSON-событие (плоский или вложенный в ANPR/AccessControllerEvent)."""
    import json

    event = ParsedEvent(raw_payload=json.dumps(data, ensure_ascii=False))

    # Развернём вложенные блоки в один уровень для поиска ключей
    flat: dict[str, object] = {}

    def _flatten(obj: object) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    _flatten(v)
                else:
                    flat.setdefault(k.lower(), v)
        elif isinstance(obj, list):
            for item in obj:
                _flatten(item)

    _flatten(data)

    def pick(*names: str) -> object | None:
        for n in names:
            if n.lower() in flat:
                return flat[n.lower()]
        return None

    plate = pick("licensePlate", "plateNumber", "plate")
    event.plate_number = str(plate) if plate is not None else None
    event.direction = _normalize_direction(
        str(pick("direction", "vehicleDirection") or "") or None
    )
    event.event_time = _parse_time(
        str(pick("dateTime", "captureTime", "time") or "") or None
    )
    cam = pick("channelName", "deviceName", "cameraName", "ipAddress")
    event.camera_name = str(cam) if cam is not None else None

    conf = pick("confidenceLevel", "confidence")
    if conf is not None:
        try:
            value = float(conf)
            event.confidence = value / 100 if value > 1 else value
        except (ValueError, TypeError):
            pass

    return event


_PLATE_PART = re.compile(r"(licensePlate|plate)", re.IGNORECASE)
_VEHICLE_PART = re.compile(r"(detection|vehicle|scene)", re.IGNORECASE)


def classify_photo(filename: str) -> str:
    """Определить тип фото по имени части: 'plate' или 'vehicle'."""
    if _PLATE_PART.search(filename):
        return "plate"
    return "vehicle"
