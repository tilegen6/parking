# ANPR Payload Reference — iDS-2CD7A46G0/P-IZHSY

Справочник формата события распознавания номера, которое камера шлёт на наш
HTTP listening server. Источник: ISAPI `EventNotificationAlert` (ANPR) +
существующий парсер `backend/src/hikvision.py`.

> Статус: **черновик по документации ISAPI**. Поля и точные имена проверяются
> съёмом реального трафика (`capture_server.py`) — см. `entry-exit-detection.md`.

## 1. Транспорт

Камера делает `POST` на наш URL. Возможны три формата тела:

| Content-Type | Что внутри | Прошивки |
|---|---|---|
| `multipart/form-data` | XML-часть `EventNotificationAlert` + JPEG-части (номер, сцена) | **основной для ANPR** |
| `application/xml` / `text/xml` | только XML, без картинок | если снимки выключены |
| `application/json` | JSON-эквивалент | редкие прошивки / прокси |

Backend уже умеет все три (`recognition._read_event`).

### Пример multipart (упрощённо)

```
POST /api/v1/hikvision/anpr-event HTTP/1.1
Content-Type: multipart/form-data; boundary=MIME_boundary

--MIME_boundary
Content-Disposition: form-data; name="anpr.xml"
Content-Type: application/xml

<EventNotificationAlert>...</EventNotificationAlert>
--MIME_boundary
Content-Disposition: form-data; name="licensePlatePicture.jpg"; filename="licensePlatePicture.jpg"
Content-Type: image/jpeg

<binary JPEG номера>
--MIME_boundary
Content-Disposition: form-data; name="detectionPicture.jpg"; filename="detectionPicture.jpg"
Content-Type: image/jpeg

<binary JPEG сцены/машины>
--MIME_boundary--
```

## 2. Ключевые поля XML

| XPath (без namespace) | Назначение | Пример | → поле backend |
|---|---|---|---|
| `eventType` | тип события | `ANPR` | (фильтр) |
| `dateTime` | время события (ISO 8601 + TZ) | `2026-06-13T10:15:32+05:00` | `event_time` |
| `channelName` | имя канала/камеры | `Entry_Camera` | `camera_name` |
| `ipAddress` | IP камеры | `192.168.1.64` | fallback `camera_name` |
| `ANPR/licensePlate` | номер | `123ABC02` | `plate_number` |
| `ANPR/direction` | направление | `forward` / `reverse` | `direction` (ENTRY/EXIT) |
| `ANPR/confidenceLevel` | уверенность 0..100 | `94` | `confidence` (→ 0..1) |
| `ANPR/plateColor` | цвет номера | `white` | — (опц.) |
| `ANPR/vehicleInfo/color` | цвет машины | `white` | — (опц.) |
| `ANPR/vehicleInfo/vehicleType` | тип ТС | `saloonCar` | — (опц.) |
| `ANPR/picName` | имя файла снимка номера | `licensePlatePicture.jpg` | привязка фото |

### Классификация снимков

`backend/src/hikvision.classify_photo()`: имя части содержит `licensePlate|plate`
→ **plate** (фото номера), иначе → **vehicle** (фото сцены). Проверить на реальных
именах частей — у некоторых прошивок это `licensePlatePicture.jpg` /
`detectionPicture.jpg`, у других `plateNo.jpg` / `vehicleImage.jpg`.

## 3. Направление (ENTRY / EXIT)

Нормализация в `hikvision._normalize_direction()`:

```
forward, in, entry, enter   → ENTRY
reverse, out, exit, leave   → EXIT
(остальное / пусто)         → UNKNOWN
```

⚠️ Поле `direction` присылается **не всегда** — зависит от настройки
"Vehicle Detection → Direction" в камере. Если камера направление не отдаёт,
направление определяется **топологией** (отдельная камера на въезд / на выезд →
по `channelName`/`ipAddress`). Это главный вопрос к натурным проверкам —
см. `entry-exit-detection.md`.

## 4. Открытые вопросы (проверить на железе)

1. Реальные имена multipart-частей и `picName`.
2. Присылает ли камера `direction`, или его эмулируем по каналу.
3. TZ в `dateTime`: локальная (`+05:00`) или UTC (`Z`)? Парсер тянет обе.
4. Сколько событий на один проезд (дубли) и с каким интервалом.
5. Формат номера для региона (латиница/кириллица, пробелы).
6. Поведение `confidenceLevel` ночью / при медленном проезде.
