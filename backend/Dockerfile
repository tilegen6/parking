# syntax=docker/dockerfile:1

FROM python:3.12-slim

# Чистый вывод логов + не плодим .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl нужен для healthcheck'а контейнера; rm для слоя поменьше
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Сначала только зависимости — слой кэшируется, пока не менялся requirements.txt
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Затем код приложения
COPY . .

# Запускаем не от root — безопаснее
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# FastAPI-приложение лежит в src/main.py как объект `app`
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
