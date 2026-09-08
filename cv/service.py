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

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from recognizer.config import RecognizerConfig  # noqa: E402
from recognizer.pipeline import Pipeline  # noqa: E402

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

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("CV_PORT", "8090")))
