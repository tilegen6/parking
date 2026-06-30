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
pytest -q          # 30 тестов: нормализация, vote, трекинг, события, качество, e2e на синтетике
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

**Что важно про реальные фото:**
- Для KZ-номеров формат-фильтр сам выбирает номер среди прочего текста на кадре — даже если в кадре есть надписи/шильдики.
- Лучше всего работают **plate-доминантные** снимки (номер крупно/по центру). На «грязных» полнокадровых сценах с мелким номером результат шумит — это ожидаемо для MVP без отдельного детектора пластины (см. ниже).
- Порог уверенности — `--confidence 0.85` (ТЗ). Ниже порога номер всё равно выводится, но помечается `low_confidence` (на ручную проверку). Снизить: `--confidence 0.5`.
- Первый запуск EasyOCR качает модели (~100 МБ) в `~/.EasyOCR/`.

### 4. Сквозная интеграция с backend

Поднимите backend (`docker compose up -d backend` из корня репозитория), затем:

```bash
python recognize.py --demo --direction entry --send-to-backend http://localhost:8000
```

События уйдут в `POST /api/v1/hikvision/anpr-event` с `source=own-cv-v1` —
в админке (`http://localhost:5173`) появятся парковочные сессии.

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
