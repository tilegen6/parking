FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Системные библиотеки: opencv-headless (glib), onnxruntime (gomp), ffmpeg (видео), curl (healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgomp1 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Лёгкий движок (numpy/opencv/fastapi/uvicorn/httpx)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Спец-движок номеров (ONNX, без torch): детекция open-image-models + OCR fast-plate-ocr.
# Лёгкий и точнее EasyOCR/generic-YOLO на реальных номерах. certifi — для скачивания моделей.
RUN pip install "fast-plate-ocr[onnx]" "open-image-models[onnx]" certifi

COPY . .

EXPOSE 8090

# /health отвечает сразу; модели EasyOCR/YOLO докачиваются при первом /recognize
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8090/health || exit 1

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8090"]
