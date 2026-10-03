"""API управления камерами: карточка, проверка связи, запуск потока в CV."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_session
from src.models import Camera, CameraStatus, RecognitionEvent
from src.schemas import CameraCheckResult, CameraCreate, CameraOut, CameraUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cameras"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Субпоток Hikvision: 101 — основной (8 MP, тяжёлый), 102 — субпоток. По сети
# (тем более через VPN) распознавать дешевле со второго.
DEFAULT_STREAM_PATH = "/Streaming/Channels/102"


def build_stream_url(camera: Camera, *, mask_password: bool = False) -> str | None:
    """Собрать URL потока камеры. None — если подключаться некуда.

    stream_url задан вручную — он и побеждает (телефон, NVR, другой вендор).
    Иначе собираем классический RTSP Hikvision из логина/пароля/IP/порта/пути.
    Пароль обязательно url-кодируем: у камер он часто содержит @ / : и без
    экранирования ffmpeg разберёт URL неправильно.
    """
    if camera.stream_url:
        return camera.stream_url
    if not camera.ip_address:
        return None
    auth = ""
    if camera.username:
        secret = "•••" if mask_password else quote(camera.password or "", safe="")
        auth = (
            f"{quote(camera.username, safe='')}:{secret}@"
            if camera.password
            else (f"{quote(camera.username, safe='')}@")
        )
    path = camera.stream_path or DEFAULT_STREAM_PATH
    if not path.startswith("/"):
        path = f"/{path}"
    return f"rtsp://{auth}{camera.ip_address}:{camera.rtsp_port}{path}"


def camera_out(camera: Camera) -> CameraOut:
    """Карточка камеры наружу: без пароля, но с понятным адресом потока."""
    out = CameraOut.model_validate(camera)
    out.has_password = bool(camera.password)
    out.stream_url_display = build_stream_url(camera, mask_password=True)
    return out


@router.get("/cameras", response_model=list[CameraOut])
async def list_cameras(session: SessionDep) -> list[CameraOut]:
    """Список зарегистрированных камер и их статус."""
    rows = (await session.execute(select(Camera).order_by(Camera.id))).scalars().all()
    return [camera_out(c) for c in rows]


@router.post("/cameras", response_model=CameraOut, status_code=201)
async def create_camera(payload: CameraCreate, session: SessionDep) -> CameraOut:
    """Зарегистрировать новую камеру в системе."""
    camera = Camera(**payload.model_dump())
    session.add(camera)
    await session.flush()
    await session.refresh(camera)
    return camera_out(camera)


@router.get("/cameras/{camera_id}", response_model=CameraOut)
async def get_camera(camera_id: int, session: SessionDep) -> CameraOut:
    camera = await _get_or_404(session, camera_id)
    return camera_out(camera)


@router.put("/cameras/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: int, payload: CameraUpdate, session: SessionDep
) -> CameraOut:
    """Обновить камеру (в т.ч. привязать к шлагбауму — gate_id)."""
    camera = await _get_or_404(session, camera_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        # Пустая строка в пароле = «не трогать»: форма не знает текущий пароль
        # и присылает пустое поле, затирать этим сохранённый пароль нельзя.
        if field == "password" and not value:
            continue
        setattr(camera, field, value)
    await session.flush()
    await session.refresh(camera)
    return camera_out(camera)


@router.delete("/cameras/{camera_id}", status_code=204)
async def delete_camera(camera_id: int, session: SessionDep) -> None:
    """Удалить камеру. События камеры удаляются каскадом (cascade у relationship)."""
    camera = await _get_or_404(session, camera_id)
    await session.delete(camera)
    await session.flush()


async def _get_or_404(session: AsyncSession, camera_id: int) -> Camera:
    camera = await session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    return camera


# --- Проверка связи и живой поток ------------------------------------------ #


@router.post("/cameras/{camera_id}/check", response_model=CameraCheckResult)
async def check_camera(camera_id: int, session: SessionDep) -> CameraCheckResult:
    """Достучаться до камеры по TCP и записать статус online/offline.

    Полноценный RTSP-хендшейк тут не нужен: если порт не открыт, дальше идти
    незачем, а если открыт — камера жива и отвечает по сети.
    """
    camera = await _get_or_404(session, camera_id)
    host, port = _probe_target(camera)
    if host is None:
        raise HTTPException(
            status_code=400,
            detail="У камеры не задан ни IP-адрес, ни URL потока — проверять нечего",
        )

    reachable, detail = await _tcp_probe(host, port)
    camera.status = CameraStatus.ONLINE if reachable else CameraStatus.OFFLINE
    if reachable:
        camera.last_seen_at = datetime.now(timezone.utc)
    await session.flush()
    return CameraCheckResult(
        camera_id=camera.id,
        reachable=reachable,
        status=camera.status,
        target=f"{host}:{port}",
        detail=detail,
    )


def _probe_target(camera: Camera) -> tuple[str | None, int]:
    """Куда стучаться: (host, port). Разбираем ручной URL, если IP не задан."""
    if camera.ip_address:
        return camera.ip_address, camera.rtsp_port
    if camera.stream_url:
        from urllib.parse import urlparse

        parsed = urlparse(camera.stream_url)
        if parsed.hostname:
            default_port = 554 if parsed.scheme == "rtsp" else 80
            return parsed.hostname, parsed.port or default_port
    return None, 0


async def _tcp_probe(host: str, port: int, timeout: float = 4.0) -> tuple[bool, str]:
    """TCP-коннект с таймаутом: (доступна, пояснение)."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True, "порт отвечает"
    except TimeoutError:
        return False, f"нет ответа за {timeout:.0f} с — проверь сеть/VPN"
    except OSError as exc:
        return False, f"соединение не установлено: {exc.strerror or exc}"


@router.post("/cameras/{camera_id}/stream/start")
async def start_camera_stream(
    camera_id: int, session: SessionDep, version: str | None = None
) -> dict[str, object]:
    """Запустить распознавание живого потока этой камеры в CV-сервисе.

    URL с паролем собирается здесь и уходит только на CV — в браузер пароль не
    попадает. Поток регистрируется под именем камеры, поэтому события вернутся
    в бэкенд уже привязанными к этой камере и её шлагбауму.
    """
    camera = await _get_or_404(session, camera_id)
    url = build_stream_url(camera)
    if not url:
        raise HTTPException(
            status_code=400,
            detail="Не из чего собрать поток: задай IP (+логин/пароль) или URL",
        )
    if camera.direction not in ("entry", "exit"):
        raise HTTPException(
            status_code=400,
            detail="У камеры не задано направление (въезд/выезд) — CV не поймёт "
            "как трактовать проезд",
        )

    body: dict[str, object] = {
        "url": url,
        "direction": camera.direction,
        "camera_name": camera.name,
    }
    if version:
        body["version"] = version
    result = await _cv_post("/stream/start", body)
    camera.status = CameraStatus.ONLINE
    camera.last_seen_at = datetime.now(timezone.utc)
    await session.flush()
    return result


@router.post("/cameras/{camera_id}/stream/stop")
async def stop_camera_stream(camera_id: int, session: SessionDep) -> dict[str, object]:
    """Остановить распознавание потока этой камеры."""
    camera = await _get_or_404(session, camera_id)
    return await _cv_post("/stream/stop", {"camera_name": camera.name})


async def _cv_post(path: str, body: dict[str, object]) -> dict[str, object]:
    """POST в CV-сервис с понятной ошибкой, если он не поднят."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(f"{settings.cv_service_url}{path}", json=body)
    except httpx.HTTPError as exc:
        logger.warning("CV-сервис недоступен (%s): %s", path, exc)
        raise HTTPException(
            status_code=503,
            detail=f"CV-сервис недоступен ({settings.cv_service_url}). "
            "Поднят ли профиль cv?",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    data: dict[str, object] = response.json()
    return data


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
