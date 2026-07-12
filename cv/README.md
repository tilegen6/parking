# cv — Hikvision Integration Lab

Лаборатория интеграции с камерой **Hikvision DeepinView iDS-2CD7A46G0/P-IZHSY**
(4 MP ANPR, распознавание номеров on-device).

Это **не** дубликат backend. Backend уже принимает события на
`POST /api/v1/hikvision/anpr-event` и парсит их (`backend/src/hikvision.py`).
Задача `cv/` — **исследовать реальную камеру**, зафиксировать её поведение и
отдать backend точную спецификацию payload'а и список граничных кейсов.

Папка закрывает группу задач **🟣 Integration / Hikvision**.

## Зачем

Камера DeepinView делает ANPR сама и шлёт событие на наш HTTP listening server.
Прежде чем доверять backend-логике ENTRY/EXIT и защите от дублей, нужно
**увидеть, что именно присылает физическая камера** в боевых условиях:
формат, поля направления, повторные срабатывания, ночь/день, медленный проезд.

## Статус и граница

`cv/` — **лаборатория интеграции**, не рантайм-сервис. Сюда же в будущем придёт
**собственная CV-модель** (отдельный деплой). Решение и путь миграции:
`docs/adr-0001-cv-as-separate-service.md`. Контракт с бэкендом (что не зависит от
того, кто распознаёт) — `contract/`.

## Структура

```
cv/
├── capture_server.py   # listening server: дампит сырой payload камеры на диск
├── replay.py           # проигрывает сохранённые/sample payload'ы в backend
├── analyze.py          # разбирает дампы, сводит статистику по полям/дублям
├── contract/           # ВЕНДОР-НЕЙТРАЛЬНЫЙ контракт recognition-события (cv→backend)
│   ├── recognition-event.md
│   ├── recognition-event.schema.json
│   └── recognition-event.example.json
├── samples/            # эталоны EventNotificationAlert (+ реальный захват)
├── captures/           # сюда падают сырые дампы с реальной камеры (gitignored)
├── docs/
│   ├── sources.md             # откуда payload + как снять с камеры (ISAPI)
│   ├── payload-format.md      # справочник формата ANPR-события
│   ├── entry-exit-detection.md# как камера сигналит направление
│   ├── test-cases.md          # сценарии для backend (handoff, replay-команды)
│   ├── camera-errors.md       # список ошибок/артефактов камеры
│   └── adr-0001-cv-as-separate-service.md
├── requirements.txt
└── .gitignore
```

## Поток данных

```
Камера (ANPR on-device)
   │  multipart/form-data: XML EventNotificationAlert + JPEG(и)
   ▼
capture_server.py  ──>  captures/<timestamp>/   (raw body, xml, images, headers.json)
   │
   ├─ analyze.py   ──>  сводка полей → docs/payload-format.md
   └─ replay.py    ──>  POST в backend /api/v1/hikvision/anpr-event (проверка end-to-end)
```

## Как запустить (черновик, реализуется в следующем цикле)

```bash
cd cv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) Поднять capture-сервер и навести на него камеру (Linkage → HTTP listening)
python capture_server.py --port 8088 --out captures/

# 2) Разобрать накопленные дампы
python analyze.py captures/

# 3) Проиграть sample/captured payload в backend
python replay.py samples/anpr_entry.xml --to http://localhost:8000/api/v1/hikvision/anpr-event
```

## Настройка камеры (для справки)

Web UI камеры → **Configuration → Network → Advanced Settings → HTTP Listening**
(или **Event → Linkage Method → Notify Surveillance Center / HTTP**). Указать
IP и порт нашего capture-сервера. Формат — `multipart/form-data` с XML-частью
`EventNotificationAlert` и вложенными снимками (номер + сцена).
