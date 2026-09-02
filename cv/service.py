#!/usr/bin/env python3
"""CV-сервис: HTTP-обёртка над распознавателем для админки.

Запуск:  python cv/service.py            # http://localhost:8090
Эндпоинты:
    GET  /health     -> {status, engine, detector, default_version, versions}
    GET  /versions   -> список версий пайплайна (v0/v1/v2)
    POST /recognize  (multipart file, опц. version) -> номер + размеченное фото

Версии пайплайна (PIPELINE_VERSIONS) переключаются на лету параметром `version`:
fastplate (v2, дефолт) | easyocr (v1, MVP) | template (v0, офлайн).
Дефолт — из env CV_VERSION (или fastplate). Порог — CV_CONFIDENCE.
"""

from __future__ import annotations

import base64
import os
import sys
import threading
from collections import deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from recognizer.config import RecognizerConfig  # noqa: E402
from recognizer.pipeline import Pipeline  # noqa: E402
from recognizer.sink import BackendSink  # noqa: E402
from recognizer.sources import DemoSource, StreamSource  # noqa: E402
from recognizer.stream import StreamPipeline  # noqa: E402

# Куда CV шлёт распознанные события (тот же приём, что у камеры). В docker —
# сервис `backend`; переопределяется env CV_BACKEND_URL или полем backend_url.
DEFAULT_BACKEND_URL = os.environ.get("CV_BACKEND_URL", "http://backend:8000")

# Лимиты загрузки (/recognize) — защита от DoS/decompression-bomb
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 МБ на файл
MAX_PIXELS = 40_000_000  # ~40 Мпикс на распакованный кадр

# Версии пайплайна распознавания — переключаются на лету (параметр version).
# Порядок = от лучшего к простому. engine = OCR-движок, detector = детектор номера.
PIPELINE_VERSIONS: dict[str, dict] = {
    "fastplate": {
        "engine": "fastplate",
        "detector": "plate",
        "label": "v2 · HF спец-модели",
        "desc": "fast-plate-ocr (OCR) + open-image-models (детектор), ONNX",
    },
    "easyocr": {
        "engine": "easyocr",
        "detector": "yolo",
        "label": "v1 · MVP",
        "desc": "EasyOCR + generic YOLOv8 (как в ТЗ для MVP)",
    },
    "template": {
        "engine": "template",
        "detector": "whole",
        "label": "v0 · офлайн",
        "desc": "template-matching по шрифту, без моделей/сети (для синтетики)",
    },
}

# какой питон-пакет нужен каждому движку/детектору (для проверки доступности)
_PKG = {
    "easyocr": "easyocr",
    "fastplate": "fast_plate_ocr",
    "yolo": "ultralytics",
    "plate": "open_image_models",
}


def _version_available(version: str) -> bool:
    """Установлены ли пакеты, нужные этой версии пайплайна."""
    import importlib.util

    v = PIPELINE_VERSIONS[version]
    needed = [_PKG[k] for k in (v["engine"], v["detector"]) if k in _PKG]
    return all(importlib.util.find_spec(m) is not None for m in needed)


def _annotate(image: np.ndarray, plate: str | None, box) -> str:
    """Нарисовать рамку и номер, вернуть data-URL PNG."""
    out = image.copy()
    if box:
        x1, y1, x2, y2 = box
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 200, 0), 3)
    cv2.putText(
        out, plate or "?", (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 200, 0), 3
    )
    ok, buf = cv2.imencode(".png", out)
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


class StreamStartReq(BaseModel):
    url: str  # rtsp://… | http://phone:8080/video | индекс вебки | "demo"
    direction: str = "entry"  # entry | exit (топология: камера въезда/выезда)
    camera_name: str = "cv-stream"
    version: str | None = None  # версия пайплайна; по умолчанию — дефолт сервиса
    backend_url: str | None = None  # переопределить приёмник событий


class _Handle:
    """Один живой поток: источник + онлайн-пайплайн + воркер-поток."""

    def __init__(
        self, camera: str, url: str, direction: str, version: str, source, sp
    ) -> None:  # noqa: ANN001
        self.camera = camera
        self.url = url
        self.direction = direction
        self.version = version
        self.source = source
        self.sp = sp
        self.thread: threading.Thread | None = None
        self.running = True
        self.error: str | None = None
        self._lock = threading.Lock()
        self._preview: tuple | None = None  # (image, plate, box)

    def set_preview(self, frame, res) -> None:  # noqa: ANN001
        if frame is None:
            return
        plate = res.plate if res else None
        box = res.box if res else None
        with self._lock:
            self._preview = (frame.image, plate, box)

    def preview(self):  # noqa: ANN202
        with self._lock:
            return self._preview


class StreamManager:
    """Держит воркеры распознавания живых потоков (по имени камеры)."""

    def __init__(self, pipeline_factory, base_conf: float) -> None:  # noqa: ANN001
        self._pf = pipeline_factory  # version -> Pipeline (с загруженными моделями)
        self._base_conf = base_conf
        self._streams: dict[str, _Handle] = {}
        self._events: deque = deque(maxlen=200)
        self._seq = 0
        self._lock = threading.Lock()

    def _build(self, req: StreamStartReq, version: str):  # noqa: ANN202
        # Реюзаем модели кэшированного пайплайна версии, но свой cfg с direction
        base = self._pf(version)
        v = PIPELINE_VERSIONS[version]
        cfg = RecognizerConfig(
            engine=v["engine"],
            detector=v["detector"],
            confidence_threshold=self._base_conf,
            direction=req.direction,
            camera_name=req.camera_name,
        )
        pipeline = Pipeline(cfg, detector=base.detector, ocr=base.ocr)
        sinks = {
            "json": [],
            "annot": [],
            "backend": [BackendSink(req.backend_url or DEFAULT_BACKEND_URL)],
        }
        sp = StreamPipeline(pipeline, cfg, sinks=sinks)
        source: DemoSource | StreamSource
        if req.url == "demo":
            source = DemoSource(target_fps=cfg.video_fps)
        else:
            source = StreamSource(
                req.url, target_fps=cfg.video_fps, name=req.camera_name
            )
        return _Handle(req.camera_name, req.url, req.direction, version, source, sp)

    def start(self, req: StreamStartReq, version: str) -> dict:
        with self._lock:
            old = self._streams.get(req.camera_name)
        if old is not None:
            self._stop_handle(old)
        handle = self._build(req, version)
        handle.thread = threading.Thread(target=self._run, args=(handle,), daemon=True)
        with self._lock:
            self._streams[req.camera_name] = handle
        handle.thread.start()
        return self.status(req.camera_name)

    def _run(self, handle: _Handle) -> None:
        try:
            for frame in handle.source.frames():
                recs = handle.sp.process(frame)
                handle.set_preview(handle.sp.last_frame, handle.sp.last_res)
                for rec in recs:
                    self._add_event(handle, rec)
        except Exception as e:  # noqa: BLE001
            handle.error = str(e)
        finally:
            handle.running = False

    def _add_event(self, handle: _Handle, rec: dict) -> None:
        br = rec.get("backend_response") or {}
        with self._lock:
            self._seq += 1
            self._events.append(
                {
                    "seq": self._seq,
                    "camera": handle.camera,
                    "plate": rec.get("plate_number"),
                    "direction": rec.get("direction"),
                    "confidence": rec.get("confidence"),
                    "flag": rec.get("flag"),
                    "backend_action": br.get("session_action"),
                    "backend_error": rec.get("backend_error"),
                    "time": rec.get("event_time"),
                }
            )

    def _stop_handle(self, handle: _Handle) -> None:
        handle.source.stop()
        if handle.thread is not None:
            handle.thread.join(timeout=5)
        handle.running = False

    def stop(self, camera: str) -> dict:
        with self._lock:
            handle = self._streams.get(camera)
        if handle is None:
            raise HTTPException(404, f"поток '{camera}' не запущен")
        self._stop_handle(handle)
        return self.status(camera)

    def stop_all(self) -> None:
        with self._lock:
            handles = list(self._streams.values())
        for h in handles:
            self._stop_handle(h)

    def status(self, camera: str | None = None) -> dict:
        with self._lock:
            handles = (
                [self._streams[camera]]
                if camera and camera in self._streams
                else list(self._streams.values())
            )
        streams = []
        for h in handles:
            src = getattr(h.source, "status", None)
            streams.append(
                {
                    "camera": h.camera,
                    "url": h.url,
                    "direction": h.direction,
                    "version": h.version,
                    "running": h.running,
                    "error": h.error,
                    "frames": h.sp.frames_seen,
                    "events": h.sp.events_emitted,
                    "last_plate": h.sp.last_plate,
                    "opened": getattr(src, "opened", None),
                    "reconnects": getattr(src, "reconnects", None),
                    "source_error": getattr(src, "last_error", None),
                }
            )
        return {"streams": streams}

    def events(self, since: int = 0) -> dict:
        with self._lock:
            items = [e for e in self._events if e["seq"] > since]
        last = items[-1]["seq"] if items else since
        return {"events": items, "last_seq": last}

    def preview(self, camera: str) -> dict:
        with self._lock:
            handle = self._streams.get(camera)
        if handle is None:
            raise HTTPException(404, f"поток '{camera}' не запущен")
        pv = handle.preview()
        if pv is None or cv2 is None:
            return {"image": None, "plate": None}
        image, plate, box = pv
        return {"image": _annotate(image, plate, box), "plate": plate}


def create_app(cfg: RecognizerConfig | None = None) -> FastAPI:
    # порог общий для всех версий; берём из cfg (тесты) или env
    base_conf = (
        float(cfg.confidence_threshold)
        if cfg
        else float(os.environ.get("CV_CONFIDENCE", "0.5"))
    )
    # дефолтная версия: из cfg (тесты подают template), иначе env, иначе fastplate
    default_version = (
        cfg.engine
        if cfg and cfg.engine in PIPELINE_VERSIONS
        else os.environ.get("CV_VERSION", "fastplate")
    )
    if default_version not in PIPELINE_VERSIONS:
        default_version = "fastplate"

    app = FastAPI(title="Smart Parking CV Service", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # кэш пайплайнов по версии — модели каждой версии грузятся лениво при 1-м запросе
    pipelines: dict[str, Pipeline] = {}

    def get_pipeline(version: str) -> Pipeline:
        if version not in pipelines:
            v = PIPELINE_VERSIONS[version]
            pipelines[version] = Pipeline(
                RecognizerConfig(
                    engine=v["engine"],
                    detector=v["detector"],
                    confidence_threshold=base_conf,
                )
            )
        return pipelines[version]

    stream_mgr = StreamManager(get_pipeline, base_conf)

    @app.get("/health")
    def health() -> dict:
        d = PIPELINE_VERSIONS[default_version]
        return {
            "status": "ok",
            "engine": d["engine"],
            "detector": d["detector"],
            "default_version": default_version,
            "versions": list(PIPELINE_VERSIONS),
        }

    @app.get("/versions")
    def versions() -> dict:
        return {
            "default": default_version,
            "versions": [
                {"name": k, "available": _version_available(k), **v}
                for k, v in PIPELINE_VERSIONS.items()
            ],
        }

    @app.post("/recognize")
    async def recognize(
        file: UploadFile = File(...),
        version: str = Form(default=default_version),
    ) -> dict:
        if cv2 is None:
            raise HTTPException(500, "opencv не установлен на сервере")
        if version not in PIPELINE_VERSIONS:
            raise HTTPException(400, f"неизвестная версия пайплайна: {version}")
        if file.size is not None and file.size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"файл больше {MAX_UPLOAD_BYTES // 1048576} МБ")
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:  # подстраховка, если size не задан
            raise HTTPException(413, f"файл больше {MAX_UPLOAD_BYTES // 1048576} МБ")
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "Не удалось прочитать изображение")
        if img.shape[0] * img.shape[1] > MAX_PIXELS:  # decompression-bomb
            raise HTTPException(413, "изображение слишком большое (пикселей)")

        try:
            res = get_pipeline(version).process_frame(img)
        except RuntimeError as e:
            # движок версии не установлен в этом образе/окружении
            raise HTTPException(400, str(e)) from e
        plate = res.plate if res and res.plate else None
        below = res.confidence < base_conf if res else True
        v = PIPELINE_VERSIONS[version]
        return {
            "plate_number": plate,
            "confidence": round(res.confidence, 3) if res else None,
            "flag": "low_confidence" if below else "ok",
            "is_valid": bool(res and res.is_valid),
            "candidates": res.alts if res else [],
            "annotated_image": _annotate(img, plate, res.box if res else None),
            "version": version,
            "engine": v["engine"],
            "detector": v["detector"],
        }

    # ── Живой поток с камеры (RTSP/телефон) ──────────────────────────────
    @app.post("/stream/start")
    def stream_start(req: StreamStartReq) -> dict:
        version = req.version or default_version
        if version not in PIPELINE_VERSIONS:
            raise HTTPException(400, f"неизвестная версия пайплайна: {version}")
        if req.direction not in ("entry", "exit"):
            raise HTTPException(400, "direction: entry | exit")
        try:
            return stream_mgr.start(req, version)
        except RuntimeError as e:  # движок версии не установлен / нет cv2
            raise HTTPException(400, str(e)) from e

    @app.post("/stream/stop")
    def stream_stop(camera_name: str = Body("cv-stream", embed=True)) -> dict:
        return stream_mgr.stop(camera_name)

    @app.get("/stream/status")
    def stream_status() -> dict:
        return stream_mgr.status()

    @app.get("/stream/events")
    def stream_events(since: int = 0) -> dict:
        return stream_mgr.events(since)

    @app.get("/stream/preview")
    def stream_preview(camera_name: str = "cv-stream") -> dict:
        return stream_mgr.preview(camera_name)

    @app.on_event("shutdown")
    def _shutdown_streams() -> None:
        stream_mgr.stop_all()

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("CV_PORT", "8090")))
