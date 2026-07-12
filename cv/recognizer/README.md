# Own CV ANPR (`own-cv-v1`)

Собственный распознаватель номеров — повторяет то, что делает ANPR-камера:
вход (картинки/видео) → детекция пластины → OCR → нормализация номера →
стабилизация (majority-vote по кадрам) → событие в вендор-нейтральном контракте
CV→backend. Закрывает раздел ТЗ 2.1–2.5.

Дизайн: [`docs/superpowers/specs/2026-06-23-own-cv-anpr-design.md`](../../docs/superpowers/specs/2026-06-23-own-cv-anpr-design.md).

## Установка

```bash
cd cv
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # numpy + opencv (лёгкий движок, без torch)
# Реальный OCR для фото (тянет torch; certifi нужен для скачивания моделей на macOS):
pip install easyocr certifi
```

## Как протестить

### 1. Автотесты (быстро, без сети/torch)

```bash
cd cv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q          # 38 тестов: нормализация, vote, трекинг, события, качество, метрики, сервис, e2e
```

### 2. Офлайн-демо (синтетические KZ-номера, движок `template`)

Генерирует 8 синтетических пластин и прогоняет весь пайплайн — без сети и моделей:

```bash
python recognize.py --demo --annotate --direction entry
# -> out/events.jsonl      (события контракта)
# -> out/annotated/*.png   (кадры с боксом и распознанным номером)
```

### 3. Реальные фото номеров (EasyOCR) — «показал фото → получил номер»

```bash
# 1) поставить реальный движок (один раз):
pip install easyocr certifi
# 2) положить свои фото в cv/photos/ и запустить:
python recognize.py photos/ --engine easyocr --annotate --direction entry
```

Результат:
- в консоли — распознанный номер по каждому фото (+ что ещё нашлось на кадре);
- `out/annotated/*.png` — кадры с подписанным номером;
- `out/events.jsonl` — события контракта.

Видео так же: `python recognize.py clip.mp4 --video --engine easyocr --direction entry`.

**Грязные полнокадровые фото — включите YOLO-детектор пластины (ТЗ «Этап 1»):**

```bash
pip install ultralytics      # один раз; модель детекции скачается автоматически
python recognize.py photos/ --engine easyocr --detector yolo --annotate --direction entry --confidence 0.5
```

YOLO находит на кадре прямоугольник номера и отдаёт OCR только его — на сценах
«машина + улица + люди + надписи» это даёт чистый номер вместо случайного текста.
Мелкие кропы автоматически апскейлятся для точности. Модель — pretrained YOLOv8
(`Koushim/yolov8-license-plate-detection`), позже заменяется дообученной на
казахстанских номерах (Roboflow/CVAT). Своя модель: `--plate-model path/to.pt`.

**Что важно про реальные фото:**
- Для KZ-номеров формат-фильтр сам выбирает номер среди прочего текста на кадре.
- Без `--detector yolo`: лучше всего работают **plate-доминантные** снимки (номер крупно). На грязных сценах — включайте YOLO (выше).
- Порог уверенности — `--confidence 0.85` (ТЗ). Ниже порога номер всё равно выводится, но помечается `low_confidence`. Снизить: `--confidence 0.5`.
- Первый запуск EasyOCR качает модели (~100 МБ) в `~/.EasyOCR/`.

### 4. Сквозная интеграция с backend

Поднимите backend (`docker compose up -d backend` из корня репозитория), затем:

```bash
python recognize.py --demo --direction entry --send-to-backend http://localhost:8000
```

События уйдут в `POST /api/v1/hikvision/anpr-event` с `source=own-cv-v1` —
в админке (`http://localhost:5173`) появятся парковочные сессии.

### 5. Оценка точности на датасете

`evaluate.py` прогоняет распознаватель по папке с **размеченными** фото и считает
метрики: точное совпадение (exact), средняя посимвольная точность (char),
доля найденных номеров (detection).

```bash
# скачать публичный датасет с эталонами (фото машин + номера):
python scripts/fetch_openalpr.py --region eu --n 25 --out datasets/openalpr_eu
# оценить (whole-frame и yolo — для сравнения):
python evaluate.py datasets/openalpr_eu --labels-from openalpr --engine easyocr --detector yolo --confidence 0.5
```

Источник разметки (`--labels-from`):
- `filename` — номер = имя файла (`123ABC02.jpg`);
- `openalpr` — `.txt` рядом с фото (`image x y w h НОМЕР`);
- `csv` — `--labels labels.csv` с колонками `filename,plate`.

**Где взять датасеты с фото номеров:**
- **openalpr/benchmarks** — реальные фото машин + эталоны (`eu`/`us`/`br`),
  скачивается скриптом выше. Удобно для проверки пайплайна.
- **Kaggle** — «Car License Plate Detection», «Large License Plate Dataset»,
  «ANPR/ALPR» наборы (нужен аккаунт Kaggle).
- **Roboflow Universe** — десятки ANPR-датасетов, есть экспорт в YOLO-формат.
- **CCPD** — крупный набор (китайские номера), номер закодирован в имени файла.
- **Для KZ-номеров** готового публичного набора практически нет — по ТЗ его
  собирают и размечают сами (Roboflow/CVAT), затем дообучают YOLO/OCR. Для быстрой
  проверки своих снимков просто кладите их в папку и используйте `--labels-from
  filename`, назвав файл номером.

### 6. Админ-страница «Тест распознавания» (загрузил фото → номер)

CV-сервис (`cv/service.py`) — HTTP-обёртка над распознавателем для админки.

```bash
# 1) поднять CV-сервис (в cv venv, где стоят easyocr/ultralytics):
python cv/service.py                    # http://localhost:8090
# 2) фронт (npm run dev / docker compose) -> открыть страницу «Тест CV» (/recognize)
#    загрузить фото -> увидеть номер + рамку
```

Эндпоинты: `GET /health`, `POST /recognize` (multipart `file`) → JSON с номером,
confidence, флагом, кандидатами и размеченным фото (base64). Движок/детектор — из env
(`CV_ENGINE`, `CV_DETECTOR`, `CV_CONFIDENCE`; дефолт `easyocr`+`yolo`). Адрес сервиса на
фронте — `VITE_CV_URL` (дефолт `http://localhost:8090`).

## Архитектура (плагинная)

| Слой | Интерфейс | MVP-дефолт | Будущее |
|------|-----------|-----------|---------|
| Детекция | `detect.PlateDetector` | `WholeFrameDetector` | `YoloPlateDetector` |
| OCR | `ocr.PlateOcr` | `TemplateOcr` / `EasyOcr` | `PaddleOcr` |
| Трекинг | `track.SimpleTracker` | IoU/centroid | ByteTrack/DeepSORT |

Движки меняются флагом `--engine` или подстановкой реализации интерфейса — пайплайн
(`pipeline.Pipeline`) и контракт события (`events.py`) не меняются.

## Контракт события

Выход соответствует [`cv/contract/recognition-event.schema.json`](../contract/recognition-event.schema.json)
(`plate_number`, `direction`, `event_time`, `confidence`, `camera_name`,
`source=own-cv-v1`, `photos`, `raw_ref`). Проверяется тестом `test_contract_matches_schema`.
