#!/usr/bin/env python3
"""CV-сервис: HTTP-обёртка над распознавателем для админки.

Запуск:  python cv/service.py            # http://localhost:8090
Эндпоинты:
    GET  /health     -> {status, engine, detector}
    POST /recognize  (multipart file) -> номер + размеченное фото (base64)

Движок/детектор берутся из env (CV_ENGINE, CV_DETECTOR, CV_CONFIDENCE);
дефолт fastplate + plate (HF-модели номеров, ONNX). Для тестов — template + whole.
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

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from recognizer.config import RecognizerConfig  # noqa: E402
from recognizer.pipeline import Pipeline  # noqa: E402


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
    cfg = cfg or RecognizerConfig(
        engine=os.environ.get("CV_ENGINE", "fastplate"),
        detector=os.environ.get("CV_DETECTOR", "plate"),
        confidence_threshold=float(os.environ.get("CV_CONFIDENCE", "0.5")),
    )
    app = FastAPI(title="Smart Parking CV Service", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    holder: dict[str, Pipeline] = {}

    def pipeline() -> Pipeline:
        if "p" not in holder:
            holder["p"] = Pipeline(cfg)
        return holder["p"]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "engine": cfg.engine, "detector": cfg.detector}

    @app.post("/recognize")
    async def recognize(file: UploadFile = File(...)) -> dict:
        if cv2 is None:
            raise HTTPException(500, "opencv не установлен на сервере")
        data = await file.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "Не удалось прочитать изображение")

        res = pipeline().process_frame(img)
        plate = res.plate if res and res.plate else None
        below = res.confidence < cfg.confidence_threshold if res else True
        is_valid = bool(res and res.is_valid)
        return {
            "plate_number": plate,
            "confidence": round(res.confidence, 3) if res else None,
            "flag": "low_confidence" if below else "ok",
            "is_valid": is_valid,
            "candidates": res.alts if res else [],
            "annotated_image": _annotate(img, plate, res.box if res else None),
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("CV_PORT", "8090")))
