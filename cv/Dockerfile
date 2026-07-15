FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Системные библиотеки: opencv-headless (glib), torch (gomp), ffmpeg (видео), curl (healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgomp1 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Лёгкий движок (numpy/opencv/fastapi/uvicorn/httpx)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Тяжёлые движки: CPU-сборка torch (намного легче CUDA) + EasyOCR + YOLO
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && pip install easyocr ultralytics certifi

COPY . .

EXPOSE 8090

# /health отвечает сразу; модели EasyOCR/YOLO докачиваются при первом /recognize
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8090/health || exit 1

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8090"]
