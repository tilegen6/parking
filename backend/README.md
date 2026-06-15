# Smart Parking — Backend (ANPR)

Backend системы умной парковки. Принимает события распознавания номеров
от камер **Hikvision (ANPR)**, сохраняет их в PostgreSQL, фото — в MinIO,
и отдаёт данные в админ-панель.

## Стек

- **FastAPI** — REST API + автодокументация (Swagger).
- **PostgreSQL** + **SQLAlchemy (async)** + **Alembic** — хранение и миграции.
- **MinIO** — фото автомобилей и номеров.
- **Redis** — очереди/кэш (зарезервировано под будущие задачи).
- **Docker Compose** — запуск всего окружения одной командой.

## Быстрый старт

```bash
cd backend
cp .env.example .env        # при необходимости поправить значения
docker compose up --build
```

Поднимутся сервисы: `postgres`, `redis`, `minio`, `backend`.
Миграции применяются автоматически при старте контейнера backend.

| Сервис            | URL                                |
|-------------------|------------------------------------|
| API (Swagger)     | http://localhost:8000/docs         |
| Health check      | http://localhost:8000/health       |
| MinIO консоль     | http://localhost:9001              |

## Локальный запуск без Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# поднять postgres/redis/minio через docker compose или локально
alembic upgrade head
uvicorn src.main:app --reload
```

## Основные эндпоинты

| Метод | Путь                              | Назначение                          |
|-------|-----------------------------------|-------------------------------------|
| POST  | `/api/v1/hikvision/anpr-event`    | Приём события от камеры Hikvision   |
| GET   | `/api/v1/recognition/events`      | Список событий (пагинация, фильтры) |
| GET   | `/api/v1/recognition/events/{id}` | Одно событие                        |
| GET   | `/api/v1/cameras`                 | Список камер                        |
| POST  | `/api/v1/cameras`                 | Добавить камеру                     |
| GET   | `/api/v1/dashboard/stats`         | Сводка для дашборда                 |
| GET   | `/health`                         | Health check                        |

### Фильтры списка событий

`/api/v1/recognition/events?page=1&limit=20&plate=777&direction=ENTRY&camera_id=1&date_from=2026-06-09&date_to=2026-06-09`

## Структура

```
src/
  config.py        # настройки из .env
  database.py      # async-движок и сессии
  models.py        # Camera, RecognitionEvent
  schemas.py       # Pydantic-схемы
  storage.py       # клиент MinIO
  hikvision.py     # парсер ANPR-событий (XML/JSON/multipart)
  main.py          # точка входа, health, CORS, обработка ошибок
  modules/
    recognition.py # приём событий + список
    camera.py      # камеры + dashboard
migrations/        # Alembic
```

## Миграции

```bash
alembic revision --autogenerate -m "описание"   # создать
alembic upgrade head                            # применить
alembic downgrade -1                            # откатить
```

## Тест ANPR-события вручную

```bash
curl -X POST http://localhost:8000/api/v1/hikvision/anpr-event \
  -H "Content-Type: application/json" \
  -d '{"licensePlate":"777ABC01","direction":"forward","dateTime":"2026-06-09T16:45:00+00:00","channelName":"Camera-1","confidenceLevel":95}'
```
