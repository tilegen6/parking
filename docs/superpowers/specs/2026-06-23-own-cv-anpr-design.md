# Design: Own CV ANPR (`own-cv-v1`)

Дата: 2026-06-23 · Статус: утверждён · Ветка: `feature/cv-own-anpr`

## Цель

Собственный модуль распознавания номеров, повторяющий то, что делает ANPR-камера:
вход (картинки/видео) → детекция пластины → OCR → нормализация номера → стабилизация
(majority-vote по кадрам) → событие в **вендор-нейтральном контракте** CV→backend
(`source=own-cv-v1`), которое можно записать локально и/или отправить в backend
(`POST /api/v1/hikvision/anpr-event`). Закрывает раздел ТЗ 2.1–2.5.

Движок распознавания — лёгкий (OpenCV + EasyOCR) за **плагинными интерфейсами**, чтобы
позже заменить на YOLOv8/PaddleOCR/ByteTrack без переписывания пайплайна.

## Где живёт

В существующем `cv/` (там уже контракт CV→backend и тулинг `replay`/`analyze`).
Новый распознаватель — подпакет `cv/recognizer/` + CLI `cv/recognize.py`.
Дублирующий `cv-service/` не заводим.

## Поток данных

```
источник (картинка/видео)
  → quality: отсев смазанных (var of Laplacian) и тёмных кадров
  → detect: регионы-кандидаты пластины (бокс + crop)
  → preprocess: grayscale → contrast(CLAHE) → denoise → sharpen
  → ocr: текст + confidence на каждый регион
  → normalize: карта путаемых символов (O→0,I→1,B→8,S→5,Z→2,G→6) + валидация формата KZ
  → [видео] track (один объект = один трек) + vote (majority за окно 2–5 c, порог conf ≥ 0.85)
  → events: сборка события контракта (direction, source=own-cv-v1, photos, event_time)
  → sink: JSON (events.jsonl) + размеченный кадр  [+ опц. POST в backend]
```

## Модули (`cv/recognizer/`)

| Модуль | Ответственность | Зависит от |
|--------|-----------------|-----------|
| `config.py` | `RecognizerConfig` (FPS, пороги, direction, движок, sink-и) | — |
| `sources.py` | `Frame`, `ImageSource` (файл/папка), `VideoSource` (кадры N FPS) | opencv (видео) |
| `quality.py` | `is_blurry`, `is_dark`, `frame_ok` | numpy |
| `preprocess.py` | `preprocess_plate` (gray→CLAHE→denoise→sharpen) | opencv/numpy |
| `detect.py` | `PlateDetector` ABC; `WholeFrameDetector` (синтетика), `EasyOcrDetector` (боксы текста) | — / easyocr |
| `ocr.py` | `PlateOcr` ABC + `OcrResult`; `TemplateOcr` (синтетика), `EasyOcr` | — / easyocr |
| `normalize.py` | `normalize_plate`, `validate_kz`, форматы `123ABC01`/`777AAA02`/`A123BCD` | — |
| `track.py` | `SimpleTracker` (IoU/centroid), один объект = один трек | numpy |
| `vote.py` | `MajorityVote` буфер по треку: выбор по (частота, conf) | — |
| `events.py` | `Direction`, `build_event` → dict контракта | — |
| `sink.py` | `JsonSink`, `AnnotatedImageSink`, `BackendSink` (POST) | opencv / httpx |
| `pipeline.py` | `Pipeline` — оркестрация всего | все выше |
| `synth.py` | Генератор синтетических KZ-номеров (тест-данные + офлайн e2e) | opencv/numpy |

CLI `cv/recognize.py`: `python recognize.py <вход> [--video] [--direction entry|exit]
[--engine template|easyocr] [--annotate] [--send-to-backend URL] [--out DIR]`.

## Контракт события (на выходе)

Соответствует `cv/contract/recognition-event.schema.json`:
`plate_number` (str|null), `direction` (`ENTRY|EXIT|UNKNOWN`), `event_time` (ISO 8601 +TZ),
`confidence` (0..1|null), `camera_name` (str|null), `source` (`own-cv-v1`),
`photos` ({plate,vehicle}), `raw_ref` (str|null).

BackendSink шлёт JSON в `POST /api/v1/hikvision/anpr-event` (backend принимает JSON-форму;
поля `plateNumber/direction/confidence/dateTime/deviceName`).

## Direction (въезд/выезд)

Источник — файлы, поэтому direction определяется:
1. флагом `--direction entry|exit`, или
2. соглашением по папке (`entry/`, `exit/`).
Инференс направления по вектору движения трека (видео) — улучшение, вне MVP-ядра.

## Движки (плагинность)

`PlateDetector` и `PlateOcr` — абстрактные интерфейсы.
- **MVP-дефолт:** `EasyOcrDetector` + `EasyOcr` (общий `easyocr.Reader`). EasyOCR — end-to-end
  локализация+чтение; детектор отдаёт регионы, OCR читает crop.
- **Офлайн/тесты:** `WholeFrameDetector` + `TemplateOcr` — детерминированно читают синтетические
  пластины из `synth.py` (без torch/сети).
- **Будущее:** `YoloPlateDetector` / `PaddleOcr` подключаются как ещё одна реализация интерфейса.

## Тестирование («как протестить»)

1. **Юнит-тесты без тяжёлых зависимостей** (`pytest`, без torch):
   `normalize` (карта символов + форматы), `vote` (majority), `track` (IoU-ассоциация),
   `events` (форма контракта), `quality` (blur/dark).
2. **Офлайн end-to-end:** `synth.py` рисует KZ-номера → `TemplateOcr` читает → весь пайплайн
   до события. Тест `test_pipeline_synth.py` проверяет: номер распознан, событие валидно по контракту.
3. **Реалистичный прогон:** `scripts/fetch_dataset.py` (опц., если есть сеть) тянет небольшой
   открытый набор фото номеров → `python recognize.py samples/ --engine easyocr --annotate`.
4. **Сквозная интеграция:** `python recognize.py samples/ --direction entry --send-to-backend
   http://localhost:8000` → события долетают, в админке появляются сессии.

## Зависимости и риск

- Ядро + офлайн-демо: `numpy`, `opencv-python` (синтетика/препроцесс), `httpx` (уже есть).
- Реальный движок: `easyocr` (тянет `torch` — увесисто). Опционален: если не поставлен/нет сети,
  CLI с `--engine easyocr` даёт понятную ошибку, а `--engine template` показывает весь пайплайн.
- Открытый датасет может не содержать именно KZ-номера → синтетика остаётся основным
  гарантированно-воспроизводимым тестом.

## Не входит в MVP (YAGNI)

RTSP-вход, YOLO/PaddleOCR, ByteTrack/DeepSORT, инференс direction по движению, дообучение на
KZ-номерах, запись кадров в MinIO. Всё — за интерфейсами/флагами, добавляется позже без слома.
