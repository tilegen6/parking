"""API распознавания: приём событий Hikvision + список событий для админки."""

import logging
import uuid
from datetime import date, datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import hikvision
from src.database import get_session
from src.models import Camera, RecognitionEvent
from src.schemas import PaginatedEvents, RecognitionEventOut
from src.storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["recognition"])


async def _resolve_camera_id(
    session: AsyncSession, camera_name: str | None
) -> int | None:
    """Сопоставить событие с зарегистрированной камерой по имени/IP."""
    if not camera_name:
        return None
    result = await session.execute(
        select(Camera.id).where(
            (Camera.name == camera_name) | (Camera.ip_address == camera_name)
        )
    )
    row = result.first()
    return row[0] if row else None


async def _read_event(request: Request) -> hikvision.ParsedEvent:
    """Разобрать тело запроса от камеры независимо от формата."""
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        event = hikvision.ParsedEvent()
        for key, value in form.multi_items():
            # Текстовые части (XML/JSON)
            if isinstance(value, str):
                if value.lstrip().startswith("<"):
                    event = hikvision.parse_xml(value)
                continue
            # Файловые части (UploadFile)
            data = await value.read()
            filename = value.filename or key
            if filename.lower().endswith((".xml",)) or data.lstrip().startswith(b"<"):
                parsed = hikvision.parse_xml(data)
                # Сохраняем поля из XML, но не теряем уже накопленные фото
                parsed.photos = event.photos
                event = parsed
            elif value.content_type and value.content_type.startswith("image/"):
                kind = hikvision.classify_photo(filename)
                event.photos[kind] = (data, value.content_type)
        return event

    body = await request.body()
    if content_type.startswith("application/json"):
        import json

        try:
            return hikvision.parse_json(json.loads(body))
        except json.JSONDecodeError:
            logger.error("Невалидный JSON от камеры")
            return hikvision.ParsedEvent(raw_payload=body.decode("utf-8", "replace"))

    # По умолчанию пробуем XML
    return hikvision.parse_xml(body)


@router.post("/hikvision/anpr-event", status_code=201)
async def receive_anpr_event(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Принять событие распознавания от камеры Hikvision и сохранить его."""
    event = await _read_event(request)
    logger.info(
        "ANPR событие: номер=%s направление=%s камера=%s",
        event.plate_number,
        event.direction,
        event.camera_name,
    )

    # Загрузка фото в MinIO
    vehicle_url = plate_url = None
    prefix = (event.plate_number or "unknown").replace(" ", "")
    for kind, (data, ctype) in event.photos.items():
        ext = "jpg" if "jpeg" in ctype or "jpg" in ctype else ctype.split("/")[-1]
        object_name = f"{prefix}/{uuid.uuid4().hex}_{kind}.{ext}"
        url = storage.upload(object_name, data, ctype)
        if kind == "plate":
            plate_url = url
        else:
            vehicle_url = url

    camera_id = await _resolve_camera_id(session, event.camera_name)

    record = RecognitionEvent(
        plate_number=event.plate_number,
        direction=event.direction,
        event_time=event.event_time or datetime.now(timezone.utc),
        confidence=event.confidence,
        camera_id=camera_id,
        camera_name=event.camera_name,
        vehicle_photo_url=vehicle_url,
        plate_photo_url=plate_url,
        raw_payload=event.raw_payload,
    )
    session.add(record)
    await session.flush()

    return {"status": "ok", "id": record.id, "plate_number": record.plate_number}


@router.get("/recognition/events", response_model=PaginatedEvents)
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    plate: str | None = Query(
        None, description="Поиск по номеру (частичное совпадение)"
    ),
    direction: str | None = Query(None, description="ENTRY / EXIT / UNKNOWN"),
    camera_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> PaginatedEvents:
    """Список событий распознавания с пагинацией и фильтрами (для таблицы в админке)."""
    conditions = []
    if plate:
        conditions.append(RecognitionEvent.plate_number.ilike(f"%{plate}%"))
    if direction:
        conditions.append(RecognitionEvent.direction == direction.upper())
    if camera_id is not None:
        conditions.append(RecognitionEvent.camera_id == camera_id)
    if date_from:
        conditions.append(
            RecognitionEvent.event_time
            >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to:
        conditions.append(
            RecognitionEvent.event_time
            <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        )

    base = select(RecognitionEvent)
    for cond in conditions:
        base = base.where(cond)

    total_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        base.order_by(RecognitionEvent.event_time.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    pages = (total + limit - 1) // limit if total else 0
    return PaginatedEvents(
        items=[RecognitionEventOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@router.get("/recognition/events/{event_id}", response_model=RecognitionEventOut)
async def get_event(
    event_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RecognitionEvent:
    """Одно событие распознавания по id."""
    from fastapi import HTTPException

    event = await session.get(RecognitionEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    return event
