"""API управления камерами."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models import Camera, CameraStatus, RecognitionEvent
from src.schemas import CameraCreate, CameraOut, CameraUpdate

router = APIRouter(prefix="/api/v1", tags=["cameras"])


@router.get("/cameras", response_model=list[CameraOut])
async def list_cameras(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Camera]:
    """Список зарегистрированных камер и их статус."""
    rows = (await session.execute(select(Camera).order_by(Camera.id))).scalars().all()
    return list(rows)


@router.post("/cameras", response_model=CameraOut, status_code=201)
async def create_camera(
    payload: CameraCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Camera:
    """Зарегистрировать новую камеру в системе."""
    camera = Camera(**payload.model_dump())
    session.add(camera)
    await session.flush()
    await session.refresh(camera)
    return camera


@router.get("/cameras/{camera_id}", response_model=CameraOut)
async def get_camera(
    camera_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Camera:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    return camera


@router.put("/cameras/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: int,
    payload: CameraUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Camera:
    """Обновить камеру (в т.ч. привязать к шлагбауму — gate_id)."""
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(camera, field, value)
    await session.flush()
    await session.refresh(camera)
    return camera


# --- Dashboard / статистика ---
dashboard_router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@dashboard_router.get("/dashboard/stats")
async def dashboard_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    """Сводка для главной страницы админки."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    events_today = (
        await session.execute(
            select(func.count())
            .select_from(RecognitionEvent)
            .where(RecognitionEvent.event_time >= today_start)
        )
    ).scalar_one()

    last_event = (
        await session.execute(
            select(RecognitionEvent)
            .order_by(RecognitionEvent.event_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    cameras_total = (
        await session.execute(select(func.count()).select_from(Camera))
    ).scalar_one()
    cameras_online = (
        await session.execute(
            select(func.count())
            .select_from(Camera)
            .where(Camera.status == CameraStatus.ONLINE)
        )
    ).scalar_one()

    return {
        "events_today": events_today,
        "last_event": {
            "plate_number": last_event.plate_number,
            "direction": last_event.direction,
            "event_time": last_event.event_time,
        }
        if last_event
        else None,
        "cameras_total": cameras_total,
        "cameras_online": cameras_online,
    }
