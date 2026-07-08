# Design: Admin «Тест распознавания» (upload photo → plate)

Дата: 2026-06-23 · Статус: утверждён · Ветка: `feature/cv-own-anpr`

## Цель

Страница в админке, где можно загрузить фото и сразу увидеть распознанный номер
с рамкой — быстрый ручной чек работы CV без CLI. Работает на готовом распознавателе
(обучение не требуется).

## Архитектура

Фронт (React) не может гонять torch/YOLO напрямую → поднимаем маленький **CV-сервис**
(FastAPI в `cv/`), как «cv-service» из ТЗ. Фронт зовёт его напрямую (CORS).

```
admin (браузер) ──multipart(file)──► cv-service POST /recognize
                                         → Pipeline (YOLO + EasyOCR)
   ◄── {plate_number, confidence, flag, is_valid, candidates, annotated_image} ──┘
   страница показывает: номер крупно + размеченное фото + confidence + кандидаты
```

## Компоненты

| Что | Файл | Делает |
|---|---|---|
| CV-сервис | `cv/service.py` | FastAPI `create_app(cfg)`; `GET /health`, `POST /recognize`; CORS; ленивый Pipeline. Порт 8090 |
| Фикс рамки | `recognizer/pipeline.py` | `process_frame` возвращает **абсолютный** бокс (для YOLO — бокс региона в координатах исходного кадра, а не кропа) |
| Страница | `frontend/src/pages/RecognizePage.tsx` | загрузка фото → POST → показ результата |
| API | `frontend/src/api/cv.ts` | `recognizePlate(file)` к cv-сервису (`VITE_CV_URL`, дефолт `http://localhost:8090`) |
| Навигация | `App.tsx` + `Sidebar.tsx` | маршрут `/recognize` + пункт «Тест CV» |
| Env | `frontend/.env.example` | `VITE_CV_URL` |

## API CV-сервиса

`POST /recognize` (multipart `file`) →
```json
{
  "plate_number": "127AST02" | null,
  "confidence": 0.98 | null,
  "flag": "ok" | "low_confidence",
  "is_valid": true,
  "candidates": ["127AST02", ...],
  "annotated_image": "data:image/png;base64,..."
}
```
`GET /health` → `{status, engine, detector}`.

Движок/детектор — из env (`CV_ENGINE`, `CV_DETECTOR`, `CV_CONFIDENCE`); дефолт
`easyocr`+`yolo`. Для тестов — `template`+`whole` (без тяжёлых моделей).

## Фикс абсолютного бокса (pipeline)

Сейчас `process_frame` отдаёт бокс OCR относительно кропа → для YOLO рамка рисуется
не там. Решение: `process_frame` собирает кандидатов как `(OcrResult, region_box)`;
`_best` пишет в `FrameResult.box` абсолютный бокс = `region_box` (если детектор дал
регион) иначе `ocr_box`. Это чинит и аннотации в `recognize.py`.

## Запуск

```bash
# CV-сервис (в cv venv, где стоят easyocr/ultralytics):
python cv/service.py            # http://localhost:8090
# фронт: npm run dev / docker compose → открыть /recognize, загрузить фото
```

## Тестирование

- `cv/tests/test_service.py`: FastAPI TestClient, движок `template`, синтетическое
  фото → проверка формы ответа и распознанного номера (без torch).
- Существующие тесты пайплайна не ломаются (фикс бокса — внутренний).
- Фронт: `npm run lint` + `npm run build`; ручная проверка страницы.

## Не входит (YAGNI)

Докеризация cv-сервиса (образ тяжёлый — позже), авторизация эндпоинта, сохранение
загрузок, очередь/Celery. Прокси через backend — альтернатива, не делаем.
