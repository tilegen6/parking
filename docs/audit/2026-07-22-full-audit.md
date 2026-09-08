# Аудит Smart Parking — 2026-07-22

Многоагентный аудит (156 агентов, адверсариальная проверка). **76 найдено / 68 выжило / 59 подтверждено.**

## Сводный план работ

Ниже — сведённый план. 68 сырых находок объединены в **44 задачи** (карта слияния — в конце, ничего не потеряно). Ранжировано по боли на боевом объекте, а не по severity-ярлыку. Пути даны относительно корня своей ветки:
- **BE** → `wt-backend/backend/` · **CV** → `wt-cv/cv/` · **FE** → `frontend/` · **DevOps** → корень репо (compose, `.github/`, Dockerfile).

**Тип работ:** ⚡ быстро (≤~30 мин, только код) · 🛠 средне (нетривиальный код, правка тестов/контракта) · 🧱 миграция БД или переделка потока/архитектуры.

---

### ⚠️ Вопрос №0 — задать заказчику ДО кодинга (блокер объёма)
**Кто физически открывает шлагбаум?** (находка #62, `barrier.py` — пустой стаб; система только пишет в лог «шлагбаум открыт/закрыт»). Если барьером рулит камера по своему allowlist — весь серверный красный список и блок недоплаты **декоративны**, и половина backend-P0 ниже теряет смысл. Если система — нужен драйвер актуатора. Пока не выяснено — оценки backend-логики условны. Это `P1-19`, но решать надо первым.

---

## P0 — до боевого запуска (деньги/безопасность, срабатывает при штатной работе)

| № | Находка (исходные #) | Ветка | Ключевые файлы | Что сделать | Тип |
|---|---|---|---|---|---|
| **P0-1** | Почти весь API без аутентификации (#13,#57,#6,#7ч,#45бэк,#53auth,#54) | BE +FE | `main.py:93-108`; роутеры `payment/tariff/camera/gate/session/recognition`; FE `App.tsx:46-56`,`Sidebar.tsx` | Default-deny: `dependencies=[Depends(get_current_user)]` на все бизнес-роутеры; мутации тарифов/шлагбаумов/камер/сессий → `require_role(ADMIN/OPERATOR)`+`record_audit`. Публичны явным whitelist: `/health`,`/auth/login`, приём камеры (по токену/allowlist — P2-7), webhook (по подписи — P0-2). На FE добавить `roles` к /tariffs,/gates,/cameras. Тесты гонять поверх `src.main.app`. | 🛠 |
| **P0-2** | Webhook без подписи + утечка `provider_payment_id` → бесплатный выезд в 2 запроса (#14,#25,#7ч) | BE | `payment.py:139-155,94-96,100-116`; `schemas.py:330` | Webhook: HMAC-подпись тела + сверка суммы/валюты + IP-allowlist. `mark_paid` искать по `(provider, provider_payment_id)`. **Читать `payload.status`** (сейчас `failed` тоже ставит paid). Убрать `provider_payment_id` из `PaymentOut`. `PAID` ставить только когда `paid_amount>=price`. | 🛠 |
| **P0-3** | `amount_due` не учитывает green/yellow — с бесплатных берут реальные деньги (#8,#26,#43) | BE +FE | BE `payment.py:49-59`, эталон `session.py:476-490`, `kaspi.py:121/169/268`; FE `lib/tariff.ts:36` | Вынести единый `price_for_session(parking,tariff,ref)` (GREEN→0, YELLOW→только после `free_until`), звать из `_handle_exit` и `amount_due`. FE `amountDue` принимать `access_type/free_until` (или брать сумму с бэка). Возврат переплат — отдельной задачей. | 🛠 |
| **P0-4** | Канонизация номера сломана: сессии матчат сырой номер (#1) + `normalize_plate` режет кириллицу (#19,#35,#49) | BE +FE | `access.py:34,39-41,110-119`, `session.py:69/103/142/297`, `recognition.py:121`,`hikvision.py`; FE `AccessListsPage.tsx:185` | В `normalize_plate` сперва транслитерировать гомоглифы (А→A…Х→X), потом чистить. Нормализовать **один раз на приёме**; хранить/сравнивать нормализованный номер в `ParkingSession`,`AccessEntry`,kaspi-lookup. В create/update_entry отклонять пустой/короткий номер (400). Миграция для сырых/пустых строк в БД. FE — превью «сохранится как …». | 🧱 |
| **P0-5** | Старт сессии сдвигается бесконечно + отказ в выезде перевзводит окно → безлимитная бесплатная парковка (#2,#9) | BE | `session.py:343,375-392,394,507` | Ввести неизменяемый якорь серии (`series_started_at`, ставится в `_open_session`); сдвигать `entry_time` только пока `ev_at−anchor ≤ entry_restart_window`; `last_seen` для окна не использовать. После `exit_denied_unpaid`/при наличии долга — запретить сдвиг `entry_time`. | 🧱 |
| **P0-6** | Жёлтый список: биллинг от `free_until` без клампа + просрочка не отсеивается + запись без даты = бесплатно навсегда (#4,#10,#20,#22) | BE +FE | `session.py:479-486,293-295`,`access.py:56-61`,`schemas.py:67/75`,`access.py:110-119`; FE `AccessListsPage.tsx:221-228,87-88` | `billable = max(0, exit_at − max(entry_time, free_until))`. При YELLOW+`free_until=None` считать как обычную платную (не 0). Требовать `valid_until` для yellow (схема+API+FE `required`, не в прошлом). | 🛠 |
| **P0-7** | Гонка ENTRY → несколько активных сессий на номер (#5,#31) | BE 🧱 | `session.py:96-109,296-308`, `models.py`(ParkingSession) | Миграция: частичный уникальный индекс `UNIQUE(plate_number, coalesce(gate_id,-1)) WHERE status='active'` (+объявить в модели). В `_handle_entry` ловить `IntegrityError`→веткой дубля; и/или `pg_advisory_xact_lock(hashtext(plate))`. | 🧱 |
| **P0-8** | CV: гонка в `StreamManager.start` → несколько живых воркеров, дубли проездов, неостановимые треды (#37) | CV | `service.py:182-192,224-228` | Всю операцию start (get→stop→build→register) под одним per-camera локом; регистрировать новый хендл только после подтверждённой остановки старого. В `_stop_handle` проверять `is_alive()`, не сбрасывать `running=False` вслепую. Кросс-хендловый дедуп по (camera+plate). | 🛠 |
| **P0-9** | CV: событие теряется при любой ошибке отправки — нет ретраев/очереди, но кулдаун и счётчик считают отправленным (#38) | CV | `sink.py:66-69`,`pipeline.py:196-201`,`stream.py:114-129` | Ретраи с бэкоффом (сеть/5xx; 4xx — не ретраить) + персистентная очередь (jsonl/sqlite) с идемпотентным ключом (camera+plate+event_time). Кулдаун и `events_emitted` — только после успешной доставки; неуспех — отдельным счётчиком в `/stream/status`. | 🛠 |

---

## P1 — высокий приоритет

| № | Находка (исходные #) | Ветка | Ключевые файлы | Что сделать | Тип |
|---|---|---|---|---|---|
| **P1-1** | Kaspi IP-allowlist обходится подделкой `X-Forwarded-For`; Basic Auth off по умолчанию (#15,#58) | BE +DevOps | `core/security.py:18-29`; compose(uvicorn), `nginx.conf` | IP брать только из доверенного источника: uvicorn `--proxy-headers --forwarded-allow-ips=<nginx>` и/или nginx перезаписывает XFF; парсить XFF справа-налево. Basic Auth обязательна при `kaspi_provider_enabled=true` (падать при пустых кредах). Сверять сумму в `pay`. Латентно — активна при боевом провайдере. | 🛠 |
| **P1-2** | Платёжный контур не идемпотентен/не атомарен: двойные платежи, гонка `paid_amount`, Kaspi-повторное списание (#12,#28,#27) | BE | `payment.py:62-81,91-97`,`session.py:207,221`,`kaspi_autopay.py:145,83-85` | `credit_session` — атомарный `UPDATE SET paid_amount=paid_amount+:amt` (или FOR UPDATE); зачислять не больше остатка. `create` — переиспользовать живой pending. Kaspi exit — детерминированный `requestId` (uuid5 от session+amount, хранить в Payment до вызова), TIMEOUT = «неизвестно» (перезапрос статуса, не слепой повтор), троттлинг. Эталон идемпотентности уже есть в `kaspi.py:132-146`. | 🛠 |
| **P1-3** | Красный список: локальная зелёная запись перебивает глобальный красный — мошенник проезжает бесплатно без сигнала (#21) | BE | `access.py:65-69`,`session.py:321` | Красный = безусловное вето: в `resolve_access` сперва `any(list_type==RED)`→вернуть красную, потом gate-specific>global среди green/yellow. Инвертировать ключ на `(priority, specific)`. | ⚡ |
| **P1-4** | ТС-9 `possible_misread` на въезде: другая машина не создаёт сессию, выхода из состояния нет (#3) | BE +FE | `session.py:404-416,441-454,152-154`,`recognition.py:245-248`,`models.py:124-127` | На въезде всё равно открывать сессию, `possible_misread` — пометкой+`Alert`(добавить `AlertKind`). Ужесточить эвристику (только O/0,I/1,B/8,S/5; не применять при высоком confidence). Дать оператору ручное создание/подтверждение. | 🛠 |
| **P1-5** | `access_entry.gate_id = ON DELETE CASCADE` — удаление шлагбаума молча стирает списки, включая красный (#32) | BE 🧱 | `models.py:164-166`,`0010_access_lists.py:38`,`gate.py:73-79` | Миграция: FK → `RESTRICT` (или блокировать удаление шлагбаума при активных `access_entry`→409). `delete/create/update_gate` → `require_role(ADMIN)`+`record_audit`. | 🧱 |
| **P1-6** | Активный тариф: FE берёт первый, BE — последний; допускается несколько активных; ноль активных → бесплатно (#47,#65) | BE +FE | BE `tariff.py:61-66,85-116`,`models.py:360`; FE `StudioPage.tsx:126`,`PaymentPage.tsx:35`,`TariffsPage.tsx:81` | Гарантировать единственный активный: в create/update снимать `is_active` с прочих в одной транзакции + частичный `UNIQUE WHERE is_active`. Нет активного → **не выпускать бесплатно**, а ошибка/алерт. FE — единый `pickActiveTariff` (как BE) или сумма с бэка. | 🧱 |
| **P1-7** | JWT-секрет не валидируется на старте (пустой→500 на логине; отсутствующий→публичный дефолт→подделка admin) (#16) | BE +DevOps | `config.py:65-66`; `.env.example:15`, compose | Убрать дефолт / `field_validator`: падать при пустом, `<32` симв. или равном дефолту при `app_env≠local`. В `.env.example` — плейсхолдер+команда генерации; compose `JWT_SECRET_KEY: ${JWT_SECRET_KEY:?}`. | ⚡ |
| **P1-8** | admin/admin: креды в дефолтах, смена не форсируется, брутфорс без лимита, логины не аудируются (#17) | BE +DevOps | `config.py:69-71`,`auth.py:136-165` | `DEFAULT_ADMIN_*` в `.env` без рабочего дефолта; при `app_env≠local` запретить пароль `admin`. Флаг `must_change_password`(миграция)+блок ручек. Лимит неудач по логину/IP. Писать `auth.login.success/failed` в audit. | 🧱 |
| **P1-9** | Пароль камеры утекает через ручной `stream_url` (CameraOut отдаёт сырым, маскирование обходится) (#53) | BE | `schemas.py:179`,`camera.py:40-41,60` | Не отдавать сырой `stream_url` в `CameraOut` (или маскировать учётку — вынести маскирование из ветки сборки в общий постпроцесс). Auth `/cameras` — из P0-1. | ⚡ |
| **P1-10** | Статус камеры `online` не сбрасывается никогда (`last_seen_at` пишется, но не читается; фонового offline нет) (#52) | BE | `recognition.py:44-45`,`camera.py:140/214/274-280`,`worker.py`(пустой) | Вычислять статус из `last_seen_at` на лету (`now−last_seen<порога`) либо периодическая задача, гасящая OFFLINE устаревшим. | 🛠 |
| **P1-11** | CV: `/stream/stop` не делает `flush()` (теряется событие открытого трека) и не удаляет хендл из `_streams` (#39) | CV | `service.py:224-236`,`stream.py:98-105` | В `_stop_handle` после join вызвать `sp.flush()`→`_add_event`, затем `_streams.pop(camera)`; сбросить `opened=False`; повторный stop→404. | 🛠 |
| **P1-12** | CV-сервис полностью без auth: произвольные `backend_url`/`url` → увод номеров/SSRF/чтение кадров (#40) | CV +DevOps | `service.py:307-312,105-111,170`,`sources.py:128-129`; compose `8090` | Убрать `backend_url` из публичного запроса (приёмник из env). `/stream/*` закрыть сервисным токеном. `allow_origins` сузить до фронта. Валидировать `url` (rtsp/http+белый список, запрет file/локальных). Не публиковать 8090 наружу (через backend-прокси). | 🛠 |
| **P1-13** | CV: `stimeout` не действует на FFmpeg 5+ (реальный таймаут 30 c, не 5) + опции в глобальный `os.environ` из треда (#41) | CV | `recognizer/sources.py:131-140` | `timeout;5000000` (+`stimeout` для FFmpeg≤4) + `CAP_PROP_OPEN/READ_TIMEOUT_MSEC` через `cap.set`; открывать капчур с per-instance params, не мутировать глобальный env. Это же гасит осиротевшие треды из P0-8. | ⚡/🛠 |
| **P1-14** | `AccessEntryUpdate` не содержит `plate` — редактирование номера молча теряется (#34,#46) | BE +FE | `schemas.py:72-77`,`access.py:141-146` | Добавить `plate:str\|None` в `AccessEntryUpdate` + применять через `normalize_plate` (или на FE не слать plate и disabled-поле). Схемам обновления `extra="forbid"`. | ⚡ |
| **P1-15** | CI ни разу не запускает Alembic + модель≠миграция (`ix_parking_session_plate_status`, `alembic check` красный); тесты на sqlite `create_all` без FK (#36,#59) | DevOps +BE | `.github/workflows/ci-cd.yml`; `models.py`(ParkingSession), `tests/conftest.py:37` | Объявить индекс в модели `__table_args__`. В CI против postgres: `alembic upgrade head && downgrade -1 && upgrade head`, `alembic heads\|wc -l==1`, `alembic check`. Часть тестов на реальном Postgres; в sqlite-фикстуре `PRAGMA foreign_keys=ON`. Снять `continue-on-error` с mypy. | 🛠 |
| **P1-16** | `/health` отдаёт 200 при недоступной БД → HEALTHCHECK/`service_healthy` бесполезны (#60) | BE +DevOps | `main.py:81-90`; `backend/Dockerfile:26-27` | При `db_ok=False` → 503 (`JSONResponse`). Развести `/health`(liveness) и `/ready`(readiness→503); HEALTHCHECK на `/ready`. | ⚡ |
| **P1-17** | Продовый образ фронта — Vite dev-сервер, собран `npm install` мимо lock, пушится в GHCR как релиз (#61) | DevOps | `frontend/Dockerfile`, `ci-cd.yml`(matrix frontend) | Multi-stage: builder `npm ci && npm run build` (VITE_* через ARG) → runtime nginx:alpine со статикой+SPA-fallback. Рантайм-адрес API — через `/config.json` энтрипоинтом (тогда убрать `VITE_API_URL` из compose). Dev-образ не пушить. | 🛠 |
| **P1-18** | Камера: направление entry/exit не участвует в push-событиях Hikvision — сессия не создаётся, хотя направление у камеры задано (#51, PLAUSIBLE) | BE | `recognition.py:114,122`,`session.py:265-274` | Если `event.direction==UNKNOWN` и камера сопоставлена и у неё задано `direction` — подставлять `camera.direction`. **Уточнить у ТЗ** (может быть by-design для push с метаданными); касается только push-пути, RTSP не затронут. | ⚡ |
| **P1-19** | Барьер физически не управляется — только лог «шлагбаум открыт/закрыт» (#62, PLAUSIBLE) | BE (арх.) | `session.py:321,506-518`,`models.py`(Gate),`barrier.py`(пустой) | См. «Вопрос №0». Если управляет система — драйвер актуатора (ISAPI-реле/GPIO/Modbus)+конфиг команды на `Gate`, вызов из `handle_recognition_event`. Если камера — зафиксировать в ТЗ, что серверные списки/блок недоплаты декоративны. | 🧱 |
| **P1-20** | CV-порог 0.5 vs backend 0.85 не согласованы — машины 0.50–0.85 «распознаны» в CV, но молча не создают сессию (#63, PLAUSIBLE) | BE/CV/DevOps | BE `config.py:51`,`session.py:123-131`; CV compose `CV_CONFIDENCE`, `service.py:292-296`,`stream.py:107-130` | Единый порог из одного источника: CV не эмитит ниже `recognition_min_confidence`, либо выровнять оба на 0.85 (ТЗ §2.4). | ⚡ |
| **P1-21** | Недоступность MinIO роняет весь приём ANPR в 500 (узкий `except S3Error`; фото грузятся до записи события) (#64, PLAUSIBLE) | BE | `storage.py:63-83`,`recognition.py:104-131` | В `upload/ensure_bucket` ловить широкий класс (`S3Error,urllib3.HTTPError,ValueError,OSError`)→None. Блок фото в recognition обернуть try/except — деградировать до «событие без фото». Хранилище фото не должно быть SPOF учёта проездов. | ⚡ |

---

## P2 — средний приоритет

| № | Находка (исходные #) | Ветка | Ключевые файлы | Что сделать | Тип |
|---|---|---|---|---|---|
| **P2-1** | Статус `UNPAID` не выставляется нигде — страница долгов и `unpaid_count` всегда пусты (#11,#33) | BE +FE | `session.py:505-516,669`,`payment.py:176`,`models.py:87`; FE `hooks.ts`(мёртвый `useUnpaidSessions`) | Считать долги по условию `status in (active,auto_closed) AND price>paid_amount`, а не по никогда не выставляемому статусу (или реально переводить в статус долга). Тест после `exit_denied_unpaid`. | 🛠 |
| **P2-2** | `valid_until` из формы без таймзоны → жёлтое окно +5 ч бесплатно; таблица и форма показывают разное время (#23,#44,#50) | FE | `AccessListsPage.tsx:87-88,75,221-229`,`lib/format.ts` | Отправлять `new Date(form.valid_until).toISOString()`; при заполнении формы UTC→локаль (не `slice(0,16)`); подписать TZ; проверить `date_from/date_to`. Бэк (`DateTime(timezone=True)`) корректен. | ⚡ |
| **P2-3** | Аудит покрывает только 5 действий — вход, отмена сессии, направление, правки тарифов/шлагбаумов/камер, оплаты не логируются (#18) | BE | `auth.py:114` (вызовы только в `user.py`/`access.py`) | После P0-1 добавить `record_audit` в login(успех/провал), `cancel_session`, `assign_event_direction`, `ack_alert`, CRUD тарифов/шлагбаумов/камер, подтверждение оплаты, Kaspi — с entity/суммой. | 🛠 |
| **P2-4** | Алерты красного списка не дедуплицируются — поток дублей вытесняет реальные сигналы за `limit(100)` (#24) | BE | `access.py:72-81,182,189-197`,`session.py:321-336` | Перед вставкой искать неподтверждённый Alert того же kind/plate/gate в окне (5 мин)→обновлять счётчик/время. Убрать `limit(100)`→пагинация/не вытеснять неподтверждённые. `ack` в audit. | 🛠 |
| **P2-5** | `event_time` из payload камеры без валидации — сбитые/будущие часы дают отрицательный `parked_seconds` и бесплатный выезд (#55) | BE | `recognition.py:123`,`hikvision.py:57-63`,`session.py:112,299` | На приёме отклонять/зажимать время сильно в будущем и подозрительно старое; наивные метки — к TZ объекта явно, не молча к UTC. | ⚡ |
| **P2-6** | Хрупкая привязка события к камере: точное `channelName==name/ip`, без нормализации и без уникальности `name` (#56) | BE | `recognition.py:24-36`,`models.py:208`,`camera.py:74` | Нормализовать сопоставление (trim/casefold); явное поле `channel_key` вместо перегрузки `name`; `UNIQUE` на ключ; при промахе/неоднозначности — лог+пометка события, а не молчаливый `gate_id=NULL`. | 🛠 |
| **P2-7** | Приём `/hikvision/anpr-event` открыт (нет auth/allowlist/требования регистрации камеры) — инъекция/реплей (#54) | BE +DevOps | `recognition.py:88`,`main.py` | Закрыть токеном камеры/mTLS или IP-allowlist (как kaspi); события от неизвестной камеры отклонять/помечать. Совмещается с whitelist из P0-1 и ограничением сдвига из P0-5. | 🛠 |
| **P2-8** | CV: фильтр качества кадра (blur/dark, ТЗ 2.1) не применяется в живом потоке — мусор перебивает голосование (#42) | CV | `stream.py:65`,`pipeline.py:135-141`,`config.py:25-27` | В `StreamPipeline.process` перед `process_frame` добавить `frame_ok(...)`, но всё равно старить треки; счётчик отброшенных в `/stream/status`. | 🛠 |
| **P2-9** | `StreamPanel` не останавливает поток CV при уходе — CV льёт фейковые проезды в боевую БД; при возврате UI показывает «Старт» (#48) | FE +CV | `StreamPanel.tsx:113-119,62,89`,`StudioPage.tsx:354` | В cleanup эффекта `stopStream(CAMERA)`+`beforeunload`/`sendBeacon`; на маунте `getStreamStatus`→восстановить `active`; убрать гонку поллинга. Радикально — TTL/heartbeat на стороне CV. | 🛠 |
| **P2-10** | Дашборд/биллинг считают «сегодня» по UTC, не Asia/Almaty (+5) — сводки и фильтры по дате сдвинуты на 5 ч (#66, PLAUSIBLE) | BE | `payment.py:161-171`,`camera.py:254-263`,`session.py:592-601`,`recognition.py:178-186` | Границы суток в TZ объекта (настраиваемый), конвертировать в UTC для сравнения. | ⚡ |
| **P2-11** | Backend не фильтрует `eventType==ANPR` — TPSRealTime засоряют очередь ручной проверки пустыми номерами (#67, PLAUSIBLE) | BE | `recognition.py:88-120`,`hikvision.py` | Извлекать `eventType`, при `!=ANPR` возвращать 200/204 без создания `RecognitionEvent` (подтверждено `cv/docs/camera-errors.md`). | ⚡ |
| **P2-12** | Kaspi deeplink с `account=session-N`, а протокол ищет `account=госномер` → оплата по ссылке всегда NOT_FOUND; двойной несвязанный платёж (pending навсегда); неизвестный `PAYMENT_PROVIDER` молча → mock (#30) | BE | `payment.py:69,33-40`,`payment_provider.py:59-65`,`kaspi.py:100,118,171-179` | `reference=parking.plate_number` (или резолвить оба формата); входящий `pay` связывать с созданным платежом по `session_id`; `PAYMENT_PROVIDER` → `Literal["mock","kaspi"]`, запрет mock при prod. Плюс `{amount}` в шаблоне не подставляется. | 🛠 |

---

## P3 — низкий / спорный

| № | Находка (исходные #) | Ветка | Ключевые файлы | Что сделать | Тип |
|---|---|---|---|---|---|
| **P3-1** | Kaspi-автосписание — `await`-HTTP на пути решения шлагбаума, до ~15 c/событие, держит соединение/транзакцию пула БД (#29, PLAUSIBLE, оспорено) | BE | `session.py:495-503,207`,`config.py:108`,`kaspi_autopay.py:74-80` | Явный `httpx.Timeout(connect=2,read=5)`+`asyncio.wait_for`; решение о выпуске — по известному `paid_amount`, списание фоном; не держать транзакцию на время HTTP. **Спорно:** один голос «намеренно/async»; магнитуда ~15 c, не 45. | 🛠 |
| **P3-2** | «Также найдено на фото» дублирует основной распознанный номер (#68) | CV/FE | `pipeline.py:108`,`service.py:385`; FE `RecognizePage.tsx:213-218` | `alts=[t[3] for t in scored[1:5] if t[3]]` или FE `candidates.filter(c=>c!==plate_number)`. | ⚡ |

---

## Пояснения к слияниям (что во что вошло)

- **P0-1** поглотил все «роутер без auth»: #6, #7(часть), #13, #45(бэк), #53(auth), #54(частично), #57. Это одна дыра «нет глобального guard».
- **P0-3 = #8+#26+#43** и **P0-4 = #1+#19+#35+#49** — один корень в двух зеркалах (бэк/фронт и сессии/списки), фиксятся единой функцией.
- **P0-5 = #2+#9**, **P0-6 = #4+#10+#20+#22**, **P0-7 = #5+#31** — буквально один баг под разными «срезами» (session-logic / billing / db-migrations).
- **P1-2 = #12+#28+#27** (идемпотентность/атомарность/повторное списание), **P1-6 = #47+#65**, **P1-14 = #34+#46**, **P1-15 = #36+#59**, **P2-1 = #11+#33**, **P2-2 = #23+#44+#50** — дубли из разных дименшенов.

## Что «5 минут», что «переделка»
- **⚡ быстрые wins (можно закрыть в первый день):** P1-3, P1-7, P1-9, P1-13, P1-14, P1-16, P1-20, P1-21, P2-2, P2-5, P2-10, P2-11, P3-2.
- **🧱 требуют миграции/переделки (планировать окно):** P0-4 (миграция данных), P0-5 (новое поле), P0-7 (уникальный индекс), P1-5 (FK), P1-6 (уникальность тарифа), P1-8 (флаг), P1-19 (архитектура/ТЗ), P2-6 (частично).
- Остальное — 🛠 средний код + правка тестов.

## Порядок работ (рекомендация)
1. **Разблокировать P1-19/Вопрос №0** — иначе часть backend-P0 бессмысленна.
2. **Безопасность одним куском:** P0-1 → P0-2 → P1-1 (после auth тесты всё равно переписывать — дешевле разом), затем P1-7, P1-9, P1-12, P2-7.
3. **Деньги:** P0-3, P0-5, P0-6, P0-7, P1-2, P1-6 (тут же миграции — планировать вместе с P0-4).
4. **CV-надёжность:** P0-8, P0-9, P1-11, P1-13.
5. **Инфра/CI как страховка:** P1-15, P1-16, P1-17 — до того, как что-то из миграций поедет в прод.
6. Хвост P2/P3 — по остаточному принципу.

Замечание: живой стенд загрязнён прогонами аудита (лишние тарифы `probe`/`AUDIT_TEST_*`, накрученные `paid_amount`, тестовые сессии `HACK2786`/`SLIDE*`/`RACE*`, два одновременно активных тарифа). Перед демо заказчику стенд надо почистить, иначе цифры биллинга считаются по подсунутому тарифу.

---

## Приложение: все находки (детали)

### [1] CRITICAL · CONFIRMED · session-logic
**Номер авто в сессиях сопоставляется «как есть» (без normalize_plate) — выезд не находит свою сессию**

- Файл: `backend/src/modules/session.py`:103
- Последствие: Если въездная и выездная камеры (разные прошивки/настройки Hikvision, разные каналы, CV-сервис vs камера) форматируют номер по-разному — «777 ABC 02» / «777ABC02» / «abc12302» — выезд НЕ находит активную сессию: барьерная логика не отрабатывает, событие уходит в event_without_session, сессия висит active вечно, оплата не начисляется вообще. Это ломает основной сценарий системы и делает ТС-1/ТС-5 недетерминированными (зависит от строки, которую прислала камера).
- Воспроизведение: Живой стенд (POST /api/v1/hikvision/anpr-event):
  entry '777 ABC 02' -> {'session_action': 'created', 'session_id': 29}
  exit  '777ABC02'   -> {'session_action': 'event_without_session', 'session_id': None}
  entry 'abc12302'   -> {'session_action': 'created', 'session_id': 30}
  exit  'ABC12302'   -> {'session_action': 'event_without_session', 'session_id': None}
psql: id 29 '777 ABC 02' status=active exit_time=NULL price=NULL; id 30 'abc12302' status=active exit_time=NULL price=NULL
- Фикс: Нормализовать номер один раз на входе (в recognition.py перед созданием RecognitionEvent или в handle_recognition_event) через access.normalize_plate и хранить/сравнивать в ParkingSession.plate_number нормализованное значение; сырой текст оставить в recognition_event.raw_payload / отдельном поле для отображения. Заодно добавить нормализацию в фильтр поиска по номеру.

### [2] CRITICAL · CONFIRMED · session-logic
**Старт сессии сдвигается бесконечно (окно считается от last_seen, а не от начала серии) — неограниченная бесплатная парковка**

- Файл: `backend/src/modules/session.py`:380
- Последствие: Машина, которую въездная камера видит хотя бы раз в 10 минут (стоянка в поле зрения камеры, разворот/повторный подъезд, водитель после отказа на выезде объезжает и повторно проезжает мимо въездной камеры), обнуляет счётчик стоянки неограниченное число раз. Прямая потеря выручки: оплата считается только за интервал между последним дублем и выездом.
- Воспроизведение: Живой стенд: 21 ENTRY для SLIDE01 с шагом 9 минут (00:00 → 03:00), затем EXIT в 03:05.
  i=1..20 -> session_action='entry_restarted' (та же сессия #9)
  EXIT -> exit_denied_unpaid, due рассчитан от 03:00
psql: id=9 SLIDE01 entry_time=2026-07-20 03:00:00+00 duration_seconds=300 price=200
Фактическая стоянка 3ч05м при тарифе 200/час = 800 KZT; система выставила 200 KZT (и так до бесконечности).
- Фикс: Считать окно от НАЧАЛА серии, а не от last_seen: хранить исходный момент первого события серии (напр. поле first_seen / не менять entry_time, а вести entry_time_original) и сдвигать старт только пока `ev_at - first_seen <= entry_restart_window_seconds`. Дополнительно ограничить суммарный сдвиг одной сессии.

### [3] CRITICAL · CONFIRMED · billing-tariff
**Весь платёжный контур и CRUD тарифов открыты без аутентификации; webhook не проверяет подпись → бесплатный выезд для любого, кто дотянулся до API**

- Файл: `backend/src/modules/payment.py`:148
- Последствие: Любой, кто видит бэкенд (в т.ч. водитель со смартфона в Wi-Fi объекта), делает 2 анонимных запроса и получает paid_amount = долг → при следующем EXIT шлагбаум открывается, деньги не заплачены. Плюс произвольно правится/удаляется тариф (price_per_hour=0 → парковка бесплатна для всех) и накручивается revenue_today на дашборде. Отдельно: PaymentWebhook не имеет ни подписи, ни секрета, ни проверки суммы — при переходе с mock на реального провайдера дыра остаётся.
- Воспроизведение: 1) curl -s -X POST http://localhost:8001/api/v1/payments/create -H 'Content-Type: application/json' -d '{"session_id":25}'  (без токена) → 201 + provider_payment_id
2) curl -s -X POST http://localhost:8001/api/v1/payments/webhook -H 'Content-Type: application/json' -d '{"provider_payment_id":"<из шага 1>","status":"paid"}' → 200 "paid"
3) docker compose exec -T postgres psql -U parking_user -d parking_db -c "select id,paid_amount from parking_session where id=25;" → 800
4) curl -s -o /dev/null -w '%{http_code}' -X DELETE http://localhost:8001/api/v1/tariffs/999999 → 404 (auth не сработал)
- Фикс: 1) Навесить auth на роутеры денег: `APIRouter(..., dependencies=[Depends(get_current_user)])` для tariff.router (а на POST/PUT/DELETE — require_role(UserRole.ADMIN)) и для /payments/create + /payments/status.
2) /payments/webhook вынести из-под пользовательской auth, но защитить как провайдерскую ручку: обязательная HMAC-подпись тела (общий секрет из settings) + сверка суммы/валюты + IP-allowlist по образцу core.security.verify_kaspi_source, который уже есть и применён к kaspi.router.
3) Добавить тест, что без токена /payments/* и мутации /tariffs отдают 401.

### [4] CRITICAL · CONFIRMED · billing-tariff
**amount_due не учитывает access_type: с зелёных и жёлтых (бесплатных) сессий берутся реальные деньги и не возвращаются**

- Файл: `backend/src/modules/payment.py`:49
- Последствие: VIP/жильцы из зелёного списка и льготники из жёлтого видят долг и платят его (через Студию, страницу оплаты или Kaspi). Механизма возврата нет: на выезде price=0, due = 0 - 800 = -800, сессия закрывается как paid, переплата навсегда остаётся на paid_amount и попадает в выручку. Это прямой сбор денег с тех, кому парковка бесплатна по договору — юридический и репутационный риск для заказчика.
- Воспроизведение: TOKEN=... ; curl -s -X POST http://localhost:8001/api/v1/access-entries -H "Authorization: Bearer $TOKEN" -d '{"plate":"777GRNX7","list_type":"green"}'
curl -s -X POST http://localhost:8001/api/v1/hikvision/anpr-event -d '{"licensePlate":"777GRNX7","direction":"forward","dateTime":"<now-3h>","confidenceLevel":95}'
curl -s -X POST http://localhost:8001/api/v1/payments/create -d '{"session_id":<id>}'  → amount=800 вместо 0
Подтвердить webhook, отправить EXIT → psql: price=0, paid_amount=800.
- Фикс: Вынести расчёт цены сессии в одну функцию (напр. `session_price(parking, tariff, ref_time)`), учитывающую access_type/free_until, и звать её и из `_handle_exit` (session.py:476-490), и из `amount_due` (payment.py:49). Тогда зелёная всегда даёт 0, жёлтая — только «перебор» после free_until. Такую же логику продублировать в frontend/src/lib/tariff.ts:36 (amountDue должен принимать access_type/free_until сессии), иначе Студия продолжит показывать долг у бесплатной машины.
Смежно (та же тема «оценка фронта ≠ расчёт бэка»): при нескольких is_active тарифах бэк берёт последний — tariff.py:64 `.order_by(Tariff.id.desc())`, а фронт первый — GET /tariffs отдаёт по возрастанию (tariff.py:81 `.order_by(Tariff.id)`), и TariffsPage.tsx:81 / StudioPage.tsx:127 делают `data?.find((t) => t.is_active)`. Уникальность активного тарифа нигде не проверяется (TariffCreate.is_active=True по умолчанию) — стоит либо гарантировать единственный активный на уровне сервиса/БД, либо отдавать фронту готовую сумму с бэка.

### [5] CRITICAL · CONFIRMED · auth-security
**Почти весь бизнес-API открыт без токена: 29 операций (тарифы, шлагбаумы, камеры, сессии, платежи, события, дашборды) доступны анонимно; роли есть только в UI**

- Файл: `backend/src/main.py`:93
- Последствие: Любой, кто дотянулся до порта бэкенда (в проде — nginx location /api/), без логина выгружает всю базу номеров/сессий/фото (персданные РК), меняет тарифы (POST/PUT/DELETE /api/v1/tariffs), удаляет шлагбаумы (DELETE /api/v1/gates/{id} — у камер и сессий gate_id обнулится), вручную закрывает и отменяет сессии, назначает направление событию (что запускает логику шлагбаума), читает выручку. Роль operator при этом технически равна admin по всему, кроме /users и /access-entries: гвард require_role стоит только в user.py:20 и access.py:31. Заявленное в ТЗ «действия с привязкой к личности» не выполняется — действия анонимны.
- Воспроизведение: 1) curl -s http://localhost:8001/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);[print(m.upper(),p,op.get('security')) for p,o in d['paths'].items() for m,op in o.items()]"
2) curl -o /dev/null -w '%{http_code}' http://localhost:8001/api/v1/tariffs  -> 200 без токена
3) curl -X POST http://localhost:8001/api/v1/parking-sessions/999999/cancel -> 404 «Сессия не найдена» (авторизация не спрашивалась)
- Фикс: Навесить аутентификацию по умолчанию на уровне приложения/роутеров (app.include_router(..., dependencies=[Depends(get_current_user)]) для camera/gate/tariff/session/payment/recognition-read/dashboard), а публичными оставить явным списком только /health, /api/v1/auth/login и приём событий камеры. Ручные операции (cancel сессии, назначение направления, CRUD тарифов/шлагбаумов/камер) закрыть require_role(OPERATOR)/require_role(ADMIN) и писать в аудит.

### [6] CRITICAL · CONFIRMED · auth-security
**POST /api/v1/payments/webhook без аутентификации и подписи + перечисляемый GET /payments/status/{id} = бесплатная парковка в два запроса**

- Файл: `backend/src/modules/payment.py`:148
- Последствие: Любой анонимный клиент перебором payment_id получает provider_payment_id всех pending-платежей и подтверждает их вебхуком: Payment -> paid, paid_amount сессии увеличивается, сессия с exit_time -> PAID, шлагбаум выпускает машину. Прямая потеря выручки и порча финансовой отчётности (/dashboard/billing считает по Payment.status == PAID). Дополнительно POST /payments/create (payment.py:128) позволяет анонимно плодить платежи по чужим сессиям.
- Воспроизведение: 1) curl -s http://localhost:8001/api/v1/payments/status/1 (без токена) — в ответе provider_payment_id.
2) curl -X POST http://localhost:8001/api/v1/payments/webhook -H 'Content-Type: application/json' -d '{"provider_payment_id":"<id из п.1>"}' — 200, платёж помечается оплаченным без каких-либо кредов.
- Фикс: Вебхук аутентифицировать: общий секрет/HMAC-подпись тела от провайдера + IP-allowlist, ключ хранить в настройках; сверять сумму из вебхука с ожидаемой. Из PaymentOut убрать provider_payment_id (или отдавать только владельцу/админу), а /payments/status закрыть аутентификацией. В credit_session ставить PAID только когда paid_amount >= начисленной суммы.

### [7] CRITICAL · CONFIRMED · access-lists
**normalize_plate вырезает кириллицу: номер, введённый кириллицей, превращается в огрызок → красный список не срабатывает**

- Файл: `backend/src/modules/access.py`:34
- Последствие: Оператор добавляет мошенника в красный список, набирая номер в русской раскладке (в форме нет ни маски, ни валидации, ни подсказки о раскладке) — запись сохраняется как «55502» или вовсе как пустая строка, UI показывает её активной и красной, но резолвер её никогда не сопоставит с реальным проездом: шлагбаум открывается, сигнала нет. Обратная сторона — коллизии: «111АВС01» и «111ХУК01» (кириллица) оба нормализуются в «11101», т.е. зелёная и красная записи схлопываются в один ключ и чужая машина может быть заблокирована или, наоборот, пропущена бесплатно. Записи с plate='' — мёртвые строки, которые resolve_access отсекает на `if not norm: return None` (access.py:54-55), т.е. защита не работает вообще.
- Воспроизведение: 1) curl -X POST localhost:8001/api/v1/access-entries -H 'Authorization: Bearer <admin>' -d '{"plate":"555АВС02","list_type":"red"}'  (буквы АВС — кириллица) → ответ plate="55502";
2) curl -X POST localhost:8001/api/v1/hikvision/anpr-event -d '{"licensePlate":"555ABC02","direction":"in","confidenceLevel":99}' → session_action="created" (машина въехала), в /api/v1/alerts пусто.
- Фикс: В normalize_plate перед вырезанием сделать гомоглиф-маппинг кириллица→латиница (А→A, В→B, Е→E, К→K, М→M, Н→H, О→O, Р→P, С→C, Т→T, У→Y, Х→X) — тот же маппинг обязателен и на стороне сравнения. Дополнительно: в create_entry/update_entry валидировать, что нормализованный номер непустой и не короче 4-5 символов, иначе 400; существующие записи с plate='' пометить как невалидные. Тест tests/test_access.py:32 покрывает только пробелы/дефис — добавить кейс с кириллицей.

### [8] CRITICAL · CONFIRMED · access-lists
**Просроченный жёлтый список: счёт считается от valid_until, а не от въезда → переплата в сотни раз (30 мин = 24 800 ₸ вместо 100 ₸)**

- Файл: `backend/src/modules/session.py`:479
- Последствие: Клиент, у которого гостевой/бронь-пропуск истёк, при стоянке 30 минут получает счёт 24 800 ₸ (124 часа × 200) вместо 100 ₸, шлагбаум не открывается («exit_denied_unpaid»), деньги списываются Kaspi-автосписанием (session.py:495-503) без участия оператора. Чем дольше запись висит просроченной, тем больше сумма — ошибка неограниченно растёт со временем. Это прямая финансовая претензия/возврат и остановка выезда.
- Воспроизведение: 1) Запись access_entry: plate=777YEL77, list_type=yellow, valid_until в прошлом (id=3 на стенде);
2) curl -X POST localhost:8001/api/v1/hikvision/anpr-event -d '{"licensePlate":"777YEL77","direction":"in","dateTime":"2026-07-22T09:30:00+00:00","confidenceLevel":99}';
3) тот же запрос с "direction":"out","dateTime":"2026-07-22T10:00:00+00:00" → exit_denied_unpaid;
4) docker compose exec -T postgres psql -U parking_user -d parking_db -c "select duration_seconds, free_until, price from parking_session where id=15;" → 1800 | 2026-07-17 06:06:57+00 | 24800.
- Фикс: Два места: (а) в session.py:479-484 считать billable от максимума: `start = max(entry, free_until)` и `billable = max(0, exit_at - start)`; (б) в resolve_access (access.py:56) учитывать срок действия — для жёлтой записи с valid_until <= now не выдавать льготу вовсе (сессия должна открываться как обычная платная), либо в _open_session (session.py:293-295) не ставить access_type=YELLOW, если valid_until уже прошёл. Тесты test_yellow_overstay_is_charged покрывают только случай valid_until в будущем.

### [9] CRITICAL · CONFIRMED · kaspi-payments
**Подтверждение оплаты (webhook) без авторизации и без подписи провайдера — бесплатная парковка в 2 запроса**

- Файл: `backend/src/modules/payment.py`:148
- Последствие: Любой, у кого есть сетевой доступ к backend (а /pay/:sessionId вообще задуман как страница для водителя), может: POST /payments/create {session_id} -> взять из ответа provider_payment_id -> POST /payments/webhook -> сессия кредитуется на любую сумму и выпускается шлагбаумом. Прямая потеря выручки; в проде с payment_provider=kaspi ручка webhook остаётся смонтированной, а mark_paid_by_provider_id (payment.py:100-116) не фильтрует по provider — можно «подтвердить» и kaspi-платёж.
- Воспроизведение: 1) curl -s http://localhost:8001/api/v1/payments/status/1 -> 200 + provider_payment_id (без Authorization); curl -o /dev/null -w '%{http_code}' http://localhost:8001/api/v1/users -> 401.
2) POST /api/v1/payments/create {"session_id": <любая активная сессия>} без токена -> 201 + provider_payment_id.
3) POST /api/v1/payments/webhook {"provider_payment_id": ...} -> платёж paid, parking_session.paid_amount += amount -> следующий EXIT-евент закрывает сессию как paid и открывает шлагбаум.
- Фикс: 1) Повесить на payment.router зависимость авторизации (как в user.py/access.py) для create/status/billing. 2) Webhook нельзя защищать JWT — ему нужна проверка подлинности провайдера: HMAC-подпись тела/IP-allowlist по аналогии с core/security.verify_kaspi_source, плюс сверка суммы и provider из payload с записью Payment. 3) mark_paid_by_provider_id должен искать по паре (provider, provider_payment_id), а не только по id. 4) Не отдавать provider_payment_id анонимным клиентам в /payments/status.

### [10] CRITICAL · CONFIRMED · db-migrations
**Нет уникального ограничения «одна активная сессия на (номер, шлагбаум)» — конкурентные ANPR-события плодят дубли активных сессий**

- Файл: `backend/src/models.py`:261
- Последствие: Одна машина = несколько параллельных активных сессий. Выезд закрывает только одну (`.first()`), остальные висят навсегда как «на парковке»: счётчик машин на парковке завышен, ТС-8 «зависшие» засоряется, kaspi `check`/`find_active_session` возвращает сумму по произвольной из дублей (можно оплатить не ту сессию и всё равно не выехать), при повторном въезде дубли уходят в auto_closed. Hikvision реально шлёт серию событий подряд, а uvicorn обрабатывает их параллельно — на проде это будет постоянно.
- Воспроизведение: На живом стенде 6 параллельных POST одного номера:
  for i in 1..6; curl -X POST localhost:8001/api/v1/hikvision/anpr-event -H 'Content-Type: application/json' -d '{"licensePlate":"RACE001TEST","direction":"forward","confidence":99,"dateTime":"2026-07-22T10:00:0$i+00:00"}' &
Ответы: created(16), created(17), created(18), created(19), created(20), updated_last_seen(19) — 5 созданий вместо 1.
psql: select id,plate_number,status,gate_id from parking_session where plate_number='RACE001TEST';
 16|RACE001TEST|active|  17|RACE001TEST|active|  18|RACE001TEST|active|  19|RACE001TEST|active|  20|RACE001TEST|active|  (5 rows)
(Это тестовые данные, оставленные проверкой: parking_session id 16–20 и recognition_event id 51–56 — их стоит вычистить.)
- Фикс: Миграцией добавить частичный уникальный индекс, который БД реально сможет держать: `CREATE UNIQUE INDEX uq_session_active_plate_gate ON parking_session (plate_number, coalesce(gate_id,-1)) WHERE status='active';` (в модели — Index(..., postgresql_where=...)), и в `_handle_entry` ловить IntegrityError → перечитать активную сессию и пойти по ветке дубля. Либо (дешевле) сериализовать обработку одного номера через `SELECT ... FOR UPDATE` по advisory-lock на hash(plate, gate_id) в начале handle_recognition_event.

### [11] CRITICAL · CONFIRMED · cv-service
**Гонка в StreamManager.start: несколько живых воркеров на одну камеру, дубли событий в бэкенд, треды неостановимы**

- Файл: `cv/service.py`:182
- Последствие: Против боевого бэкенда каждый осиротевший тред самостоятельно шлёт POST /api/v1/hikvision/anpr-event -> дублирующиеся въезды/выезды и дублирующиеся парковочные сессии по одной машине. Осиротевшие треды недостижимы: их нет в _streams, поэтому ни /stream/stop, ни stop_all() (service.py:238-242, итерирует только _streams) их не останавливают — они живут до перезапуска процесса, держат VideoCapture и продолжают писать в БД. /stream/status при этом врёт (running=false у живого треда, заниженные счётчики).
- Воспроизведение: 1) 4 параллельных `curl -X POST http://localhost:8090/stream/start -d '{"url":"demo","camera_name":"race2","version":"template"}'`; 2) подождать 20 c; 3) `curl -X POST /stream/stop -d '{"camera_name":"race2"}'`; 4) `curl '/stream/events?since=N'` — события с camera=race2 продолжают появляться после stop, с повторяющимися номерами.
- Фикс: Всю операцию start (получить старый -> остановить -> собрать -> зарегистрировать) выполнять под одним локом (или под per-camera локом), а регистрацию нового хендла делать только после подтверждённой остановки старого. В _stop_handle после join проверять `handle.thread.is_alive()`: не выставлять running=False вслепую, а возвращать ошибку/оставлять пометку 'stopping' и не отдавать имя камеры под новый поток, пока старый тред жив. Дедупликацию по номеру вынести на уровень StreamManager (общий cooldown по camera+plate), чтобы даже при накладке не уходили дубли в бэкенд.

### [12] CRITICAL · CONFIRMED · cv-service
**Событие теряется навсегда при любой ошибке отправки в бэкенд: нет ретраев и очереди, но счётчик и кулдаун считают его отправленным**

- Файл: `cv/recognizer/sink.py`:66
- Последствие: Любой транзиентный сбой (рестарт backend, миграция alembic на старте, 500/таймаут БД, сетевой блип) = безвозвратная потеря события въезда. Машина физически въехала, но сессии в БД нет; на выезде бэкенд не найдёт открытую сессию -> тариф не начислится / шлагбаум отработает по неверной ветке. Хуже: кулдаун уже проставлен, поэтому если та же машина будет распознана повторно в течение cooldown_seconds=60 (config.py:23), событие подавится и вторично — окно потери расширяется до минуты. Внешне в UI событие выглядит успешным (flag="ok").
- Воспроизведение: `curl -X POST http://localhost:8090/stream/start -H 'Content-Type: application/json' -d '{"url":"demo","direction":"entry","camera_name":"audit-probe","version":"template","backend_url":"http://127.0.0.1:9"}'`, подождать ~15 c, затем `curl 'http://localhost:8090/stream/events?since=0'` — события с backend_error и backend_action=null; счётчик events в /stream/status растёт, повторных POST нет.
- Фикс: В BackendSink добавить ретраи с экспоненциальным бэкоффом и джиттером на сетевые ошибки/таймауты/5xx (4xx — не ретраить, логировать отдельно), плюс персистентную очередь недоставленных событий (файл jsonl или SQLite рядом с сервисом) с фоновой досылкой и идемпотентным ключом (camera+plate+event_time), чтобы бэкенд мог отсеять повторы. Кулдаун проставлять только после успешной доставки (или откатывать при неуспехе). events_emitted инкрементить только при backend_response, а неуспех отражать отдельным счётчиком в /stream/status.

### [13] CRITICAL · CONFIRMED · frontend-correctness
**Фронт выставляет счёт машинам из зелёного/жёлтого списка — бесплатный проезд превращается в реальный платёж**

- Файл: `frontend/src/lib/tariff.ts`:36
- Последствие: Сессия #32 (зелёный список) попадает в StudioPage в блок «К оплате · долги» (StudioPage.tsx:317-319: `.map((s) => ({ session: s, due: amountDue(s, activeTariff) })).filter((x) => x.due > 0)`), в SessionsPage у неё показывается ссылка «Оплатить», а на /pay/32 PaymentPage рисует «К оплате 800 ₸» и активную кнопку оплаты (PaymentPage.tsx:36 `const due = s ? amountDue(s, activeTariff) : 0;`). Нажатие кнопки реально создаёт платёж и зачисляет деньги в сессию, которая по правилам списков стоит 0. Обратный случай тоже ломается: жёлтая сессия внутри free_until получает due>0, а на выезде бэкенд насчитывает 0 — оператор видит долг там, где его нет, и наоборот, PaymentPage.tsx:52 (`due <= 0 ? «Долга нет — можно выезжать ✓»`) может показать «долга нет» жёлтой сессии, которая уже перебрала free_until.
- Воспроизведение: 1) На стенде: `curl -s -X POST -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d '{"plateNumber":"911GRN11","direction":"ENTRY","confidence":0.97,"dateTime":"<now-3h>Z"}' http://localhost:8001/api/v1/hikvision/anpr-event` → session_id=32, access_type=green.
2) Открыть http://localhost:5173/studio → блок «К оплате · долги» содержит 911GRN11 с суммой 800 ₸ и кнопкой «Оплатить»; либо открыть /pay/32 — «К оплате 800 ₸».
3) Выпустить ту же машину (EXIT) без оплаты — бэкенд посчитает price=0 и откроет шлагбаум, то есть платить было не за что.
- Фикс: Расширить amountDue до полного зеркала логики выезда: принимать `Pick<ParkingSession, "parked_seconds"|"paid_amount"|"access_type"|"free_until"|"entry_time">` и возвращать 0 при access_type==="green"; при "yellow" считать биллинг только за интервал после free_until (`Math.max(0, (Date.now() - Date.parse(free_until))/1000)`), как это делает session.py:479-484. Ещё надёжнее — вообще не считать деньги на клиенте: добавить на бэке `GET /api/v1/parking-sessions/{id}/due` и показывать серверную сумму, оставив estimatePrice только как справочную «оценку» без кнопки оплаты.

### [14] CRITICAL · CONFIRMED · frontend-ux
**Списки доступа: номер, набранный кириллицей, молча превращается в пустую строку — запись создаётся, но НИКОГДА не срабатывает**

- Файл: `frontend/src/pages/AccessListsPage.tsx`:185
- Последствие: В Казахстане оператор набирает номер в русской раскладке («777АВС02» — А/В/С кириллические). Форма принимает, API отвечает 200, запись появляется в таблице (с пустым или обрезанным номером на плашке) — и красный список для этой машины не работает вообще: мошенника пускают, сигнала нет. Никакой ошибки/предупреждения оператор не видит. То же самое ломает зелёный/жёлтый (человек платит, хотя должен ехать бесплатно).
- Воспроизведение: 1. Логин admin/admin → «Списки доступа». 2. В поле «Номер *» набрать 777АВС02 русскими буквами, список «Красный», Добавить. 3. Запись создаётся (200), в таблице плашка номера пустая/обрезанная. 4. Проверить: `docker compose exec -T postgres psql -c "select id,plate,note from access_entry order by id desc limit 3"` → plate='' (см. строку id=5 на стенде). 5. Прогнать этот номер через /api/v1/hikvision/anpr-event — красный список не срабатывает.
- Фикс: В AccessListsPage перед отправкой нормализовать номер тем же правилом, что и бэкенд, плюс транслитерировать кириллические омоглифы (А→A, В→B, Е→E, К→K, М→M, Н→H, О→O, Р→P, С→C, Т→T, У→Y, Х→X). Показывать под полем превью «будет сохранено как: 777ABC02» и блокировать сабмит, если после нормализации остаётся пустая строка или длина < 4. Ту же нормализацию применить в фильтрах Сессий/Событий по номеру.

### [15] CRITICAL · CONFIRMED · tests-ci-config
**Все API кроме /users и /access-* открыты без аутентификации; ни один тест этого не проверяет (цепочка «бесплатный выезд»)**

- Файл: `backend/src/main.py`:93
- Последствие: Любой, кто дотянулся до порта бэкенда, читает все сессии/номера/камеры, правит тарифы и шлагбаумы, и — главное — может пометить чужой платёж оплаченным (перебор целочисленного payment_id в /payments/status выдаёт provider_payment_id, затем /payments/webhook закрывает долг). Прямые денежные потери на каждом выезде. Плюс ложное чувство защищённости: логин/роли/аудит написаны и покрыты тестами, но применены к 2 роутерам из 10.
- Воспроизведение: 1) curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/api/v1/parking-sessions -> 200
2) curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8001/api/v1/tariffs -H 'Content-Type: application/json' -d '{"name":"probe","free_minutes":0,"price_per_hour":1,"is_active":false}' -> 201
3) curl -s http://localhost:8001/api/v1/payments/status/1 -> отдаёт provider_payment_id
4) POST /api/v1/payments/webhook {"provider_payment_id": "<из шага 3>"} закроет долг (шаг не выполнялся, чтобы не менять данные).
- Фикс: Навесить `dependencies=[Depends(get_current_user)]` на APIRouter'ы camera/gate/tariff/session/recognition/payment (и require_role(ADMIN) на мутации тарифов/камер/шлагбаумов), оставив публичными только /health, /auth/login и вебхуки провайдеров с собственной проверкой. Убрать provider_payment_id из PaymentOut и/или закрыть /payments/webhook подписью (HMAC от провайдера). В тесты добавить параметризованный набор «каждый мутирующий эндпоинт без токена -> 401» поверх src.main.app, а не поверх ad-hoc FastAPI().

### [16] CRITICAL · CONFIRMED · tests-ci-config
**IP-allowlist Kaspi обходится подделкой X-Forwarded-For; Basic Auth выключена дефолтом — тест проверяет только отрицательный случай**

- Файл: `backend/src/core/security.py`:18
- Последствие: После включения KASPI_PROVIDER_ENABLED=true (боевой режим оплаты) эндпоинт GET /api/kaspi/pay становится фактически публичным: любой шлёт `X-Forwarded-For: 194.187.247.152` и командой command=pay начисляет произвольную сумму на любой номер — kaspi.py:86 кредитует сессию и открывает выезд. Деньги в системе появляются без реальной оплаты.
- Воспроизведение: Тест из репо доказывает, что решение принимается по заголовку: tests/test_kaspi_provider.py:146 с X-Forwarded-For: 9.9.9.9 -> 403. Симметрично, `curl -H 'X-Forwarded-For: 194.187.247.152' 'http://host/api/kaspi/pay?command=pay&txn_id=1&account=123ABC02&sum=200.00'` пройдёт allowlist (на живом стенде роутер не смонтирован, т.к. kaspi_provider_enabled=false).
- Фикс: Брать IP только из request.client.host, запуская uvicorn с --proxy-headers --forwarded-allow-ips=<IP nginx>, либо читать X-Forwarded-For исключительно когда peer входит в список доверенных прокси. Сделать Basic Auth обязательной при kaspi_provider_enabled=true (валидация в Settings), сравнивать пароль через secrets.compare_digest. Добавить тесты: (а) разрешённый IP в peer -> 200, (б) поддельный X-Forwarded-For с разрешённым IP при недоверенном peer -> 403, (в) kaspi_provider_enabled=true + пустой username -> отказ старта.

### [17] HIGH · CONFIRMED · session-logic
**ТС-9 (possible_misread) на ВЪЕЗДЕ проглатывает легитимный автомобиль: сессия не создаётся вообще**

- Файл: `backend/src/modules/session.py`:404
- Последствие: Реальная другая машина, номер которой отличается на 1 символ от любой активной сессии, въезжает без сессии: не тарифицируется, не попадает в «на парковке», а на выезде снова получает possible_misread. Полная потеря учёта и денег по этому автомобилю + неверная занятость парковки. Плюс в ответе API возвращается session_id ЧУЖОЙ сессии (near.id), что вводит фронт в заблуждение.
- Воспроизведение: Живой стенд:
  A entry 111AAA01 -> {'session_action': 'created', 'session_id': 24}
  B entry 111AAA02 -> {'session_action': 'possible_misread', 'session_id': 24}
  B exit  111AAA02 -> {'session_action': 'possible_misread', 'session_id': 24}
psql: в parking_session есть только 24 / 111AAA01. Машина 111AAA02 простояла 5 часов, price=NULL, сессии нет.
- Фикс: На ВЪЕЗДЕ сессию всё равно открывать (машина физически заезжает), а possible_misread ставить как ПОМЕТКУ на событии/сессии для ручного разбора. Дополнительно ужесточить эвристику: учитывать только «визуально похожие» пары (O/0, I/1, B/8, S/5) вместо любого отличия в один символ, и не применять её, когда confidence высокий.

### [18] HIGH · CONFIRMED · session-logic
**Жёлтый список: платное время считается от free_until, а не от въезда; просроченные/бессрочные записи не проверяются**

- Файл: `backend/src/modules/session.py`:483
- Последствие: 1) Просроченный жёлтый пропуск: стоянка 1 час считается как ~71 час → счёт 14200 вместо 200 KZT, выезд запрещён (exit_denied_unpaid) — машина физически заперта на парковке до «доплаты» несуществующего долга. 2) Жёлтая запись без valid_until = вечная бесплатная парковка, барьер открывается всегда.
- Воспроизведение: Прогон логики на изолированной SQLite-БД (docker compose exec backend python, тариф 200/час):
  777YEL01 (yellow, valid_until=2026-07-18 12:00, стоял ровно 1ч 2026-07-21 10:00→11:00):
    entry=created exit=exit_denied_unpaid duration=3600s price=14200.0 status=active
  888YEL02 (yellow, valid_until=None, тот же 1ч):
    entry=created exit=closed duration=3600s price=0.0 status=paid
  999PAY03 (обычная, тот же 1ч): price=200.0
- Фикс: Считать billable как `max(0, exit_at - max(entry_time, free_until))`. В resolve_access отбрасывать записи с истёкшим valid_until (или явно трактовать их как обычные платные). В AccessEntryCreate/Update требовать valid_until для list_type='yellow' (иначе 400), либо задавать дефолтный срок.

### [19] HIGH · CONFIRMED · session-logic
**Гонка при параллельных ENTRY: создаётся несколько активных сессий на один номер (нет блокировки/уникального ограничения)**

- Файл: `backend/src/modules/session.py`:96
- Последствие: Дубли ANPR-событий приходят пачкой (ретраи Hikvision, две камеры на одном шлагбауме, CV-сервис + камера) — на один заезд создаётся N активных сессий. EXIT закрывает только одну (order_by entry_time desc → .first()), остальные висят active бесконечно: завышенный счётчик «машин на парковке», мусор в ТС-8 (stale), а при следующем выезде того же номера снова находится «активная» сессия и с водителя повторно требуют оплату.
- Воспроизведение: Живой стенд: 6 одновременных потоков с ОДНИМ И ТЕМ ЖЕ событием ENTRY (RACE01, dateTime 2026-07-21T10:00:00+00:00):
  5 ответов 'created' (session_id 10,11,12,13,14) + 1 'entry_restarted'
psql: 5 строк RACE01 status=active, одинаковый entry_time.
После EXIT (2026-07-21T11:00:00+00:00): затронута только #10 (exit_denied_unpaid, price=200); #11–#14 остались active с price=NULL.
- Фикс: Сериализовать обработку номера: SELECT ... FOR UPDATE по существующей сессии + pg_advisory_xact_lock(hashtext(plate)) на время handle_recognition_event, и/или частичный уникальный индекс `CREATE UNIQUE INDEX ... ON parking_session (plate_number, coalesce(gate_id,-1)) WHERE status='active'` с обработкой IntegrityError как «дубль».

### [20] HIGH · CONFIRMED · session-logic
**Эндпоинты управления сессиями и направлением события доступны без авторизации**

- Файл: `backend/src/modules/session.py`:692
- Последствие: Любой, у кого есть сетевой доступ к backend, без токена может: получить весь список сессий с номерами машин (утечка ПДн), отменить активную сессию (cancelled → долг обнуляется, при выезде машина уходит бесплатно) и назначить событию направление EXIT, закрыв сессию. Это ручные операторские действия по шлагбауму — они защищены ролями в UI, но не на API, и не попадают в audit_log.
- Воспроизведение: Живой стенд, без заголовка Authorization:
  GET  /api/v1/parking-sessions                      -> HTTP 200 (полный список)
  POST /api/v1/parking-sessions/999999/cancel        -> HTTP 404 {"detail":"Сессия не найдена"}   (т.е. до бизнес-логики дошли, 401 не выдан)
  POST /api/v1/recognition/events/999999/direction   -> HTTP 404 {"detail":"Событие не найдено"}
для сравнения: GET /api/v1/users -> HTTP 401 {"detail":"Not authenticated"}
- Фикс: Навесить Depends(get_current_user) на чтение и require_role(UserRole.OPERATOR) на cancel_session и assign_event_direction (плюс record_audit по образцу access.py), оставив публичным только /hikvision/anpr-event (и его защитить IP-allowlist/токеном камеры).

### [21] HIGH · CONFIRMED · billing-tariff
**Отказ в выезде обновляет last_seen и тем самым «перевзводит» окно сдвига въезда: следующее ENTRY-событие обнуляет время стоянки**

- Файл: `backend/src/modules/session.py`:507
- Последствие: Стоянка любой длительности превращается в минимальный тариф (а при free_minutes > 0 — в 0). Сценарий бытовой, а не хакерский: водителю не открыли шлагбаум, он сдал назад / развернулся и снова попал в кадр въездной камеры того же шлагбаума (in/out камеры на одном КПП смотрят в общую зону) — и счёт обнулился. Систематическая потеря выручки, при этом в БД остаётся entry_adjusted=t, но исходное время въезда уже затёрто (восстанавливать придётся по recognition_event вручную).
- Воспроизведение: P=555FREE5
curl -X POST :8001/api/v1/hikvision/anpr-event -d '{"licensePlate":"'$P'","direction":"forward","dateTime":"<now-5h>","confidenceLevel":95}'
curl ... '{"direction":"reverse","dateTime":"<now>"}'   → exit_denied_unpaid
curl ... '{"direction":"forward","dateTime":"<now+20s>"}' → entry_restarted
psql: select entry_time,price,entry_adjusted from parking_session where plate_number='555FREE5'; → entry_time = now, price 200 вместо 1000
- Фикс: Разделить «последнее событие на въезде» и «последнее событие вообще»: завести отдельное поле (напр. last_entry_seen) и сравнивать окно сдвига только с ним, не с last_seen, который обновляется выездом. Дополнительно запретить сдвиг entry_time, если по сессии уже был отказ в выезде / есть начисленный долг или платежи (paid_amount > 0, duration_seconds is not None) — тогда после denied exit старт сессии заморожен.

### [22] HIGH · CONFIRMED · billing-tariff
**Жёлтый список без valid_until = бесплатная парковка навсегда: валидации нет ни в схеме, ни в форме, ни в расчёте**

- Файл: `backend/src/modules/session.py`:479
- Последствие: Жёлтый список задуман как «бесплатно ДО момента X, дальше по тарифу», но запись с пустым «Бесплатно до», сохранённая через обычную форму администратора, даёт пожизненный бесплатный проезд — фактически второй зелёный список, только незаметный: в таблице списков стоит «жёлтый», в колонке «Бесплатно до» — прочерк. Тихая потеря выручки, которую по UI не отличить от корректной записи.
- Воспроизведение: curl -X POST :8001/api/v1/access-entries -H "Authorization: Bearer $TOKEN" -d '{"plate":"444YELNO","list_type":"yellow"}'   (valid_until не передаём — ровно как делает форма с пустым полем)
curl -X POST :8001/api/v1/hikvision/anpr-event -d '{"licensePlate":"444YELNO","direction":"forward","dateTime":"<now-3h>","confidenceLevel":95}'
curl -X POST :8001/api/v1/hikvision/anpr-event -d '{"licensePlate":"444YELNO","direction":"reverse","dateTime":"<now>","confidenceLevel":95}' → "closed"
psql: select price,paid_amount from parking_session where plate_number='444YELNO'; → 0 | 0
- Фикс: 1) Валидация на бэке: в AccessEntryCreate/Update — model_validator, требующий valid_until при list_type == "yellow" (и запрещающий valid_until в прошлом при создании); тот же контроль в access.create_entry/update_entry.
2) Безопасный дефолт в расчёте: session.py:479 — если access_type == YELLOW и free_until is None, считать как обычную платную сессию (billable = duration), а не как бесплатную.
3) Во фронте — required на поле «Бесплатно до» при выборе «Жёлтый» (AccessListsPage.tsx:221).

### [23] HIGH · CONFIRMED · auth-security
**IP-allowlist Kaspi обходится подделкой заголовка X-Forwarded-For (nginx его не перезаписывает, Basic Auth по умолчанию выключена)**

- Файл: `backend/src/core/security.py`:18
- Последствие: Когда включат боевой провайдер (KASPI_PROVIDER_ENABLED=true), единственная защита денежного эндпоинта GET /api/kaspi/pay снимается одной строкой заголовка. Атакующий шлёт command=pay&account=<номер>&sum=1 с подделанным XFF и получает Payment(status=paid) + credit_session, а из-за payment.py:94-96 выехавшая сессия становится PAID при оплате 1 тенге. Также command=check превращается в анонимный поиск по номеру авто (есть ли машина на парковке и сколько должна).
- Воспроизведение: docker compose exec -T backend python -c "from starlette.requests import Request; from src.core.security import _client_ip; print(_client_ip(Request({'type':'http','headers':[(b'x-forwarded-for',b'194.187.247.152, 10.0.0.5')],'client':('10.0.0.5',1234)})))"  -> 194.187.247.152 (spoofed IP принимается allowlist'ом)
- Фикс: Брать IP только из доверенного источника: список trusted proxies и разбор XFF справа налево, либо nginx `proxy_set_header X-Forwarded-For $remote_addr;` (перезапись, а не добавление) + чтение X-Real-IP. Сделать Basic Auth обязательной при kaspi_provider_enabled=true (падать на старте, если креды пустые), сверять сумму в pay с amount_due и логировать все входящие вызовы Kaspi.

### [24] HIGH · CONFIRMED · auth-security
**JWT-секрет не валидируется на старте: пустой (как в .env.example) ломает вход 500-й, отсутствующий молча включает публичный дефолт «dev-insecure-change-me»**

- Файл: `backend/src/config.py`:66
- Последствие: Вариант A: развёртывание по .env.example стартует, /health отвечает ok, но КАЖДЫЙ логин отдаёт 500 с обезличенным текстом — система нерабочая и причину по ответу не видно. Вариант B (забыли переменную в systemd/k8s/CI): токены подписываются общеизвестной строкой из репозитория — любой подделает {"sub":"1","role":"admin"} и получит полный админ-доступ, включая /users и /audit-log. Ни один из вариантов не диагностируется на старте.
- Воспроизведение: docker compose exec -T -e JWT_SECRET_KEY= backend python -c "from src.config import settings; print(repr(settings.jwt_secret_key)); from src.models import User,UserRole; from src.modules.auth import create_access_token; u=User(username='a',password_hash='x',role=UserRole.ADMIN,is_active=True); u.id=1; create_access_token(u)"  -> '' + InvalidKeyError
docker compose exec -T backend sh -c "env -u JWT_SECRET_KEY python -c 'from src.config import settings; print(repr(settings.jwt_secret_key))'"  -> 'dev-insecure-change-me'
- Фикс: Убрать дефолт (jwt_secret_key: str без значения) либо добавить field_validator: падать на старте, если секрет пуст, короче 32 символов или равен дефолту при app_env != local. В .env.example положить явный плейсхолдер с командой генерации, в docker-compose.yml добавить JWT_SECRET_KEY: ${JWT_SECRET_KEY:?не задан в .env}.

### [25] HIGH · CONFIRMED · auth-security
**Стартовый админ admin/admin: пароль зашит в дефолты, не выводится в .env/.env.example, смена не форсируется, брутфорс логина ничем не ограничен и не аудируется**

- Файл: `backend/src/modules/auth.py`:136
- Последствие: Любая инсталляция по умолчанию пускает злоумышленника под admin с логином admin/admin: полный доступ к пользователям, спискам доступа (в т.ч. добавить свой номер в зелёный список) и аудиту. Отсутствие ограничения попыток делает перебор паролей и остальных учёток бесплатным, а отсутствие аудита входов — незаметным: по журналу невозможно установить факт и источник взлома.
- Воспроизведение: 1) curl -s -X POST http://localhost:8001/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin"}' -> 200 + admin-токен (живой стенд).
2) grep -iE 'admin' .env .env.example -> DEFAULT_ADMIN_* отсутствуют, переопределить пароль штатным конфигом нельзя.
3) docker compose exec -T postgres psql -U parking_user -d parking_db -c "select action,count(*) from audit_log group by action;" -> событий входа нет.
- Фикс: Вынести DEFAULT_ADMIN_USERNAME/DEFAULT_ADMIN_PASSWORD в .env(.example) без рабочего дефолта; при app_env != local отказываться стартовать с паролем «admin». Добавить пользователю флаг must_change_password и блокировать все ручки, кроме смены пароля, пока он взведён. Ввести счётчик неудачных попыток (по логину и IP) с задержкой/блокировкой и писать auth.login.success / auth.login.failed в audit_log.

### [26] HIGH · CONFIRMED · access-lists
**Резолвер: запись на конкретный шлагбаум перебивает глобальную по цвету — зелёная локальная запись отменяет глобальный красный список**

- Файл: `backend/src/modules/access.py`:65
- Последствие: Штатный сценарий «занести мошенника в красный список на все шлагбаумы» бесшумно не срабатывает, если на этот номер когда-то заводили зелёную/жёлтую запись на конкретный КПП (бывший сотрудник, старая бронь). Машина проезжает, причём бесплатно (access_type=green → price=0 на выезде, session.py:476-478), и сигнал ответственному не уходит. В UI (AccessListsPage) обе записи показаны активными, никакого предупреждения о конфликте нет — оператор уверен, что доступ закрыт.
- Воспроизведение: Код детерминирован: resolve_access вернёт запись с максимальным (specific, priority). Записи: (plate='X', red, gate_id=NULL) и (plate='X', green, gate_id=1). Событие с камеры, привязанной к gate_id=1 → conds (access.py:60) выбирают обе строки, _key даёт (0,3) и (1,2), max → зелёная → session.py:321 не срабатывает, вызывается _open_session(..., access=green) → сессия открыта, price=0.
- Фикс: Красный должен быть безусловным вето: в resolve_access сначала проверять `any(e.list_type == RED for e in rows)` и возвращать красную запись, и только потом разбирать gate-specific > global среди зелёных/жёлтых. Либо инвертировать ключ на (priority, specific). Плюс в CRUD предупреждать/запрещать создание зелёной/жёлтой записи на номер, у которого уже есть активная красная.

### [27] HIGH · CONFIRMED · access-lists
**Жёлтая запись без valid_until = бессрочно бесплатно (валидации нет ни в схеме, ни в create_entry, ни в форме)**

- Файл: `backend/src/modules/access.py`:110
- Последствие: Жёлтый список по ТЗ — «бесплатно до срока, далее по тарифу». Запись без даты молча превращается в вечный зелёный: оператор добавил гостя, не заполнил необязательное поле «Бесплатно до» — машина ездит бесплатно неограниченно долго. В таблице такая запись выглядит как обычная жёлтая («Бесплатно до: —»), отличить её от корректной нельзя. Прямая утечка выручки, при этом видимых признаков ошибки нет.
- Воспроизведение: 1) POST /api/v1/access-entries {"plate":"444YELNO","list_type":"yellow"} (без valid_until) → 201, valid_until=null;
2) ANPR entry, затем ANPR exit через 3 часа → session_action="closed";
3) psql: price=0, status=paid при тарифе 200 ₸/час и duration_seconds=10810.
- Фикс: В AccessEntryCreate/Update добавить валидатор: list_type == 'yellow' ⇒ valid_until обязателен и должен быть в будущем (иначе 400). Продублировать в форме (required при выборе «Жёлтый»). Защитно в session.py:293-295: если access.list_type == YELLOW и valid_until None — не помечать сессию как льготную (считать по тарифу), чтобы None не читался как «бесплатно навсегда».

### [28] HIGH · CONFIRMED · kaspi-payments
**amount_due не учитывает зелёный/жёлтый списки — бесплатные машины выставляются к оплате и реально платят (живой пример: 800 ₸ с зелёного номера)**

- Файл: `backend/src/modules/payment.py`:49
- Последствие: Kaspi check по номеру из зелёного списка вернёт result=0 и сумму долга, Kaspi pay спишет деньги, /payments/create создаст платёж — за парковку, которая по бизнес-правилу бесплатна (скорая, VIP). Деньги списаны, возврата в системе нет, при выезде price=0 и переплата просто зависает в paid_amount. То же для жёлтого списка: игнорируется free_until, водитель платит за льготное время.
- Воспроизведение: psql: select id,plate_number,status,access_type,price,paid_amount from parking_session where id=7; -> green, price=0, paid_amount=800; select * from payment where session_id=7; -> amount=800 status=paid. Любой новый ENTRY зелёного номера + POST /api/v1/payments/create снова даст сумму > 0 (amount_due считает по тарифу 200 ₸/ч, ceil по часам).
- Фикс: Вынести из session.py:_handle_exit единый price_for_session(parking, tariff) (GREEN -> 0, YELLOW -> тариф только на время после free_until) и использовать его в amount_due; тогда check/pay/create станут согласованы с логикой шлагбаума. Тот же баг зеркалится на фронте — frontend/src/lib/tariff.ts:amountDue тоже считает без access_type.

### [29] HIGH · CONFIRMED · kaspi-payments
**Kaspi-автосписание: повторный EXIT-евент = повторное списание с новым requestId, таймаут трактуется как отказ — риск двойного/тройного списания с карты**

- Файл: `backend/src/modules/session.py`:207
- Последствие: Машина стоит перед закрытым шлагбаумом, камера перечитывает номер каждые несколько секунд — на каждое событие уходит отдельный POST /api/parking/exit с новым requestId. Если первый вызов упал по TIMEOUT/сетевой ошибке, а списание у Kaspi прошло — водителя спишут повторно (3 евента = до 3 списаний одной и той же суммы), и ни одно из них не будет отражено как PAID (в Payment пишется только FAILED с error_code=TIMEOUT).
- Воспроизведение: 1) Включить kaspi_autopay_enabled. 2) Сессия с долгом (777YEL77 / id=15). 3) Отправить подряд 3 EXIT-евента (см. вывод выше — все три доходят до расчёта due и до ветки автосписания). Каждый вызов уйдёт в Kaspi с новым uuid requestId.
- Фикс: 1) Детерминированный requestId (например uuid5 от (parking_session_id, попытка/сумма)) и сохранение его в Payment ДО обращения к Kaspi — тогда ретрай попадёт в идемпотентность Kaspi. 2) TIMEOUT обрабатывать как «неизвестно»: не повторять списание вслепую, а перезапрашивать статус по requestId. 3) Троттлинг попыток по сессии (не чаще N секунд / не более M попыток), чтобы серия дублей EXIT не превращалась в серию списаний.

### [30] HIGH · CONFIRMED · kaspi-payments
**Гонка на paid_amount: credit_session делает read-modify-write без блокировки — параллельные зачисления затирают друг друга**

- Файл: `backend/src/modules/payment.py`:93
- Последствие: Два зачисления по одной сессии в одном окне (Kaspi pay + подтверждение webhook, ретрай Kaspi с новым txn_id, автосписание одновременно с оплатой в приложении) — второй UPDATE перезаписывает первый: деньги в payment записаны дважды, а paid_amount вырос один раз. Итог: водитель оплатил, шлагбаум продолжает считать долг (или наоборот — сессия закрыта как PAID при частичной оплате). Ручной разбор и возвраты.
- Воспроизведение: Два параллельных запроса на одну сессию: POST /api/v1/payments/webhook по двум разным provider_payment_id одной сессии (в БД такие пары уже есть: payment id=2 и id=3 оба на session_id=25 по 800). Оба читают paid_amount=X, оба пишут X+800 -> в сессии окажется X+800 вместо X+1600. Аналогично для одновременного входящего /api/kaspi/pay и autopay-списания.
- Фикс: Зачислять атомарно: `await session.execute(update(ParkingSession).where(id==...).values(paid_amount=ParkingSession.paid_amount + amount))` либо брать строку через `select(...).with_for_update()`. Статус PAID выставлять только когда покрыт весь долг (paid_amount >= price), а в kaspi._handle_pay сверять пришедший sum с amount_due и отдавать код ошибки при недоплате, а не result=0.

### [31] HIGH · CONFIRMED · db-migrations
**access_entry.gate_id стоит ON DELETE CASCADE (у всех остальных — SET NULL): удаление шлагбаума молча стирает списки доступа, включая красный; DELETE /gates при этом без авторизации**

- Файл: `backend/src/models.py`:164
- Последствие: Удаление шлагбаума безвозвратно и молча уничтожает все привязанные к нему записи списков доступа — в том числе красный список (запреты проезда) и жёлтые абонементы. Ни подтверждения, ни следа в audit_log, хотя для access_entry аудит специально заведён (access.create/update/delete). Так как эндпоинт не требует токена, стереть списки может кто угодно, у кого есть сетевой доступ к API.
- Воспроизведение: 1) Разница ON DELETE — вывод pg_constraint выше (CASCADE только у access_entry).
2) Отсутствие авторизации: `curl -s -o /dev/null -w '%{http_code}' -X DELETE http://localhost:8001/api/v1/gates/999999` → 404 (`{"detail":"Шлагбаум не найден"}`), а не 401/403 — Bearer не требуется. То же видно в openapi.json: у /api/v1/gates/{gate_id} DELETE поле security отсутствует, тогда как у /api/v1/access-entries — security=[{'HTTPBearer': []}].
- Фикс: Миграцией пересоздать FK как ON DELETE SET NULL (тогда запись становится глобальной — что тоже опасно) либо RESTRICT/блокировать удаление шлагбаума при наличии активных access_entry, вернув 409 с подсказкой «сначала перенесите/удалите записи списков». Плюс закрыть delete_gate/create_gate/update_gate ролью (require_role(UserRole.ADMIN)) и писать record_audit.

### [32] HIGH · CONFIRMED · db-migrations
**Статус SessionStatus.UNPAID не выставляется нигде в коде — страница «долги» и счётчик unpaid_count всегда пустые**

- Файл: `backend/src/models.py`:87
- Последствие: Заявленная функция учёта долгов не работает: `GET /api/v1/parking-sessions/unpaid` («Сессии, выехавшие без оплаты (долги)») всегда возвращает [], `unpaid_count` на денежном дашборде всегда 0. Оператор не видит ни одного должника, хотя недоплатившие машины реально существуют — они просто лежат со статусом active и неотличимы от стоящих на парковке.
- Воспроизведение: curl -s http://localhost:8001/api/v1/parking-sessions/unpaid  →  []
curl -s http://localhost:8001/api/v1/dashboard/billing  →  {"revenue_today":1600.0,"unpaid_count":0,"avg_parked_seconds":3635}
(при этом в parking_session есть сессии с price>paid_amount)
psql: select status, count(*) from parking_session group by status;  — строки 'unpaid' нет ни одной.
- Фикс: Либо реально выставлять UNPAID (например, при ручном пропуске должника оператором / при auto_closed с непогашенным долгом), либо переписать оба запроса на условие долга по данным, а не по статусу: `where status in ('active','auto_closed') and coalesce(price,0) - paid_amount > 0.009`, и убрать неиспользуемые константы UNPAID/WHITELIST из SessionStatus, чтобы они не вводили в заблуждение.

### [33] HIGH · CONFIRMED · db-migrations
**AccessEntryUpdate не содержит поля plate, а фронт шлёт его в PUT — редактирование номера в списке доступа молча не применяется**

- Файл: `backend/src/schemas.py`:71
- Последствие: Пользователь правит номер в форме «Списки доступа», получает 200 и сброс формы (onSuccess: reset) — но номер в БД остаётся прежним. Для красного списка это дыра: опечатку в номере нарушителя исправить через UI нельзя, старый (чужой) номер продолжает блокироваться, а нужный — беспрепятственно проезжает. При этом в audit_log пишется «access.update» с detail из присланных полей, т.е. журнал утверждает, что правка была.
- Воспроизведение: curl -s http://localhost:8001/openapi.json | jq '.components.schemas.AccessEntryUpdate.properties | keys'
→ ["gate_id","is_active","list_type","note","valid_until"]  — plate отсутствует.
Сценарий в UI: «Списки» → «Изменить» у записи → поменять номер → «Сохранить» → форма закрывается без ошибки, в таблице (и в psql `select id,plate from access_entry`) номер прежний.
- Фикс: Добавить в AccessEntryUpdate `plate: str | None = Field(None, min_length=1, max_length=32)` и в update_entry нормализовать его: `if "plate" in data: data["plate"] = normalize_plate(data["plate"])` (с проверкой на пустоту, см. отдельную находку). Для защиты от таких рассинхронов поставить схемам обновления `model_config = ConfigDict(extra="forbid")`, чтобы лишнее поле давало 422, а не тихо терялось.

### [34] HIGH · CONFIRMED · cv-service
**/stream/stop не вызывает StreamPipeline.flush() (теряется событие открытого трека) и не удаляет хендл из _streams**

- Файл: `cv/service.py`:224
- Последствие: 1) Машина, стоящая перед шлагбаумом в момент остановки/перезапуска потока, имеет открытый трек — он молча выбрасывается вместе с хендлом, событие въезда не создаётся (ровно тот сценарий, ради которого flush() и написан и покрыт тестом test_flush_closes_open_track). 2) Остановленные потоки навсегда остаются в _streams: /stream/status отдаёт мусорные записи с противоречивым running=false/opened=true, повторный /stream/stop возвращает 200 вместо 404 (фронт не отличает «остановил» от «не было»), /stream/preview продолжает отдавать устаревший кадр давно мёртвого потока. 3) Каждый такой хендл вечно удерживает в _preview полный кадр (для 1080p ~6 МБ) — медленная утечка памяти по числу использованных имён камер.
- Воспроизведение: 1) `POST /stream/start {"url":"demo","camera_name":"audit-probe","version":"template"}`; 2) `POST /stream/stop {"camera_name":"audit-probe"}` -> 200; 3) повторный `POST /stream/stop {"camera_name":"audit-probe"}` -> снова 200 (ожидалось 404); 4) `GET /stream/preview?camera_name=audit-probe` -> 200 с картинкой; 5) `GET /stream/status` — запись висит бесконечно.
- Фикс: В _stop_handle после join вызывать `for rec in handle.sp.flush(): self._add_event(handle, rec)` (только если тред действительно завершился), а затем удалять запись: `with self._lock: self._streams.pop(handle.camera, None)`. В stop() возвращать статус до удаления. Дополнительно сбрасывать source.status.opened=False в DemoSource.stop()/StreamSource при выходе, чтобы status не противоречил сам себе.

### [35] HIGH · CONFIRMED · cv-service
**CV-сервис полностью без аутентификации: /stream/start принимает произвольные backend_url и url (увод номеров на чужой хост, SSRF во внутреннюю сеть)**

- Файл: `cv/service.py`:393
- Последствие: Остальная система уже под JWT+ролями (коммиты про вход/роли/аудит), а CV — открытая control-plane: любой, кто дотянулся до :8090 (в т.ч. через CORS * из любой вкладки браузера оператора), может (а) запустить поток с backend_url на свой сервер и получать поток распознанных госномеров, времён и имён камер — утечка ПДн; (б) заставить сервис слать POST на внутренние адреса docker-сети (minio:9000, postgres, grafana) — SSRF; (в) подсунуть url = путь к локальному файлу или чужой RTSP/HTTP и через /stream/preview выкачивать кадры; (г) заDoSить сервис пачкой стартов (тредов) и — через дыру из находки 1 — навсегда занять имена камер.
- Воспроизведение: Без токена: `curl -s -X POST http://localhost:8090/stream/start -H 'Content-Type: application/json' -d '{"url":"demo","direction":"entry","camera_name":"audit-probe","version":"template","backend_url":"http://127.0.0.1:9"}'` -> 200 и поток стартует; события начинают уходить на указанный адрес (в логе /stream/events виден backend_error от этого адреса).
- Фикс: Убрать backend_url из публичного запроса (адрес бэкенда — только из env CV_BACKEND_URL), а если возможность нужна — валидировать по белому списку хостов. Закрыть мутирующие эндпоинты (/stream/start, /stream/stop) проверкой того же JWT/сервисного токена, что и у backend, ограничить allow_origins конкретным origin фронта, валидировать url по схеме (rtsp/http/https + белый список хостов, запрет file/локальных путей) и не публиковать 8090 на хост (ходить через backend-прокси).

### [36] HIGH · CONFIRMED · cv-service
**stimeout не действует на FFmpeg 5+: заявленный 5-секундный таймаут RTSP не работает (реально 30 c), плюс опции пишутся в глобальный os.environ из воркер-треда и не снимаются**

- Файл: `cv/recognizer/sources.py`:131
- Последствие: Опция игнорируется, поэтому реальный порог зависания — дефолтные 30 c OpenCV, а не 5 c. Прямое следствие: join(timeout=5) в StreamManager._stop_handle (service.py:227) на мёртвой/подвисшей камере ВСЕГДА истекает — это и есть механизм, порождающий осиротевшие треды из находки 1 (замерено: рестарт того же camera_name занял 5.391 c). Плюс на подвисшем (но открытом) RTSP кадр не читается 30 c, всё это время /stream/status показывает running=true, opened=false, source_error=null — оператор не видит, что камера мертва. Отдельно: OPENCV_FFMPEG_CAPTURE_OPTIONS пишется в глобальный os.environ процесса из воркер-треда и никогда не очищается — это гонка с одновременным открытием других источников и «залипание» RTSP-опций на последующих MJPEG/вебка-потоках.
- Воспроизведение: `docker compose exec -T cv python -c "import os,time; os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']='rtsp_transport;tcp|stimeout;3000000'; import cv2; t=time.time(); c=cv2.VideoCapture('rtsp://192.0.2.1:554/x'); print(c.isOpened(), time.time()-t)"` -> False, ~30.7 c вместо 3 c.
- Фикс: Задавать обе формы для совместимости: `rtsp_transport;tcp|timeout;5000000|stimeout;5000000` (в FFmpeg ≥5 работает timeout, в ≤4 — stimeout), и дополнительно выставлять `OPENCV_FFMPEG_READ_ATTEMPTS`/`CAP_PROP_OPEN_TIMEOUT_MSEC` и `CAP_PROP_READ_TIMEOUT_MSEC` через cap.set, а не только env. Env не мутировать глобально — открывать капчур через `cv2.VideoCapture(target, cv2.CAP_FFMPEG, params)` с per-instance параметрами. В _stop_handle согласовать join-таймаут с фактическим таймаутом источника и проверять is_alive().

### [37] HIGH · CONFIRMED · frontend-correctness
**«Бесплатно до» (жёлтый список) уходит на бэк без таймзоны — окно льготы смещается на весь offset пользователя**

- Файл: `frontend/src/pages/AccessListsPage.tsx`:88
- Последствие: Оператор в Казахстане (Asia/Almaty, UTC+5) вводит «бесплатно до 18:00», система хранит 18:00 UTC = 23:00 по Алматы — гость катается бесплатно на 5 часов дольше, чем разрешил оператор (прямая потеря выручки). На текущей машине стенда (TZ +08) расхождение 8 часов. Дополнительно ломается сама страница: в форме поле показывает 18:00, а строка таблицы для той же записи покажет 24.07 02:00 — два разных значения одного поля на одном экране.
- Воспроизведение: 1) Логин админом, /access-lists → «Добавить в список», список «Жёлтый», номер 777YEL99, «Бесплатно до» = 23.07.2026 18:00, Добавить.
2) `curl -s -H "Authorization: Bearer $T" http://localhost:8001/api/v1/access-entries` → у новой записи `"valid_until":"2026-07-23T18:00:00Z"` (введённые 18:00 записаны как 18:00 UTC).
3) В таблице на той же странице столбец «Бесплатно до» покажет 24.07.2026 02:00 (на хосте с TZ +08) — не то, что вводили.
- Фикс: Отправлять абсолютный момент: `valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null` (datetime-local интерпретируется как локальное время, toISOString даёт корректный UTC). Для обратного заполнения формы вместо `.slice(0,16)` конвертировать UTC→локаль, например `const d = new Date(en.valid_until); const pad = (n:number)=>String(n).padStart(2,"0"); const v = ${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`. То же самое сделать превентивно для любых будущих datetime-local полей.

### [38] HIGH · CONFIRMED · frontend-correctness
**Роль-зависимая навигация неполная: оператор штатно попадает на /tariffs, /gates, /cameras и может удалить тариф, по которому считаются деньги**

- Файл: `frontend/src/App.tsx`:49
- Последствие: Оператор (роль operator) видит в меню «Тарифы» и «Шлагбаумы», открывает их и получает полностью рабочие кнопки «изменить»/«удалить» (TariffsPage.tsx:251-263, GatesPage.tsx:205-217). Удаление/правка активного тарифа мгновенно меняет суммы для всех сессий и может обнулить биллинг парковки; удаление шлагбаума развязывает зоны у камер и сессий. Комментарий в App.tsx:32 «админ-панель за логином» тоже не выполняется: критичные GET (сессии, тарифы, события) отдаются вообще без токена, так что весь ролевой контроль существует только в UI.
- Воспроизведение: 1) Создать пользователя с ролью operator на /users, войти под ним.
2) В сайдбаре виден пункт «Тарифы»; открыть /tariffs (или прямым URL /gates) — страница рендерится полностью, кнопки «изменить»/«удалить» активны.
3) Нажать «удалить» на активном тарифе — DELETE /api/v1/tariffs/{id} вернёт 204, тариф исчезнет (бэкенд не проверяет ни роль, ни токен: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/v1/tariffs` → 200 без Authorization).
- Фикс: 1) Во фронте завести единую карту доступа: добавить `roles: ["admin"]` пунктам /tariffs, /gates, /cameras в Sidebar.tsx (как уже сделано для /users и /access-lists) и обернуть соответствующие <Route> в App.tsx тем же условием, чтобы прямой URL уходил на `<Navigate to="/" replace />`. 2) Обязательно продублировать на бэке — навесить AdminDep на POST/PUT/DELETE в modules/tariff.py, modules/gate.py, modules/camera.py и общую авторизацию на GET-ручки; без этого фронтовый гард ничего не защищает.

### [39] HIGH · CONFIRMED · frontend-correctness
**Редактирование номера в списках доступа молча не сохраняется — форма рапортует об успехе**

- Файл: `frontend/src/pages/AccessListsPage.tsx`:84
- Последствие: Заявленная в последнем коммите функция «списки — редактирование … (полное управление)» для номера не работает. Оператор исправляет опечатку в номере из красного списка (например 666RED66 → 666RED67), видит закрывшуюся форму и «сохранено», но в базе остаётся старый номер: нужная машина продолжает проезжать, а по чужому номеру продолжают идти сигналы 🚨. Ошибка не всплывает нигде — ни тоста, ни 4xx, ни расхождения в таблице (после инвалидации списка номер просто останется прежним, что легко принять за «не туда нажал»).
- Воспроизведение: 1) Логин админом, /access-lists, у записи 666RED66 (красный) нажать «изменить».
2) Поменять номер на 666RED67, нажать «Сохранить» → форма закрывается без ошибки.
3) `curl -s -H "Authorization: Bearer $T" http://localhost:8001/api/v1/access-entries | grep 666RED` → номер остался 666RED66, изменились только прочие поля; в аудите запись `access.update` с detail из перечня применённых полей, где plate нет.
- Фикс: Согласовать контракт: либо добавить `plate: str | None = Field(None, min_length=1, max_length=32)` в AccessEntryUpdate и применять его через normalize_plate в access.py:141-146, либо (если номер намеренно неизменяем) во фронте не слать plate в PUT (`const { plate, ...patch } = payload`), сделать поле «Номер» disabled в режиме editId != null и подписать «номер менять нельзя — удалите и создайте запись». Заодно типизировать патч отдельным `AccessEntryPatch` вместо `Partial<AccessEntryInput>`, чтобы TS ловил лишние поля.

### [40] HIGH · CONFIRMED · frontend-ux
**Списки доступа: «Бесплатно до» уезжает на часовой пояс — жёлтый список даёт лишние 5 часов бесплатной парковки**

- Файл: `frontend/src/pages/AccessListsPage.tsx`:221
- Последствие: Оператор задаёт «бесплатно до 18:00», а система бесплатно пускает до 23:00 (для Алматы UTC+5) — 5 часов парковки бесплатно на каждой жёлтой записи, деньги мимо кассы. Плюс одно и то же поле показывает РАЗНОЕ время в таблице (23:00) и в форме редактирования (18:00) — оператор не понимает, чему верить.
- Воспроизведение: 1. «Списки доступа» → жёлтый, номер 333ABC02, «Бесплатно до» = сегодня 18:00, Добавить. 2. В таблице колонка «Бесплатно до» покажет 23:00:00. 3. `curl -s localhost:8001/api/v1/access-entries -H "Authorization: Bearer $T"` → "valid_until":"...T18:00:00Z" (уже готовая строка id=3 на стенде). 4. Нажать «изменить» — в поле снова 18:00.
- Фикс: Отправлять ISO со смещением: `new Date(form.valid_until).toISOString()`; при заполнении формы конвертировать обратно в локальное (`toLocaleString`/ручной сдвиг на `getTimezoneOffset()`), а не `slice(0,16)`. Рядом с полем подписать таймзону («время местное, GMT+5»). Проверить те же места для фильтров date_from/date_to.

### [41] HIGH · CONFIRMED · camera-onboarding
**Статус online не сбрасывается никогда: last_seen_at пишется, но не читается, фонового механизма offline нет — мёртвая камера и упавший CV-поток вечно «онлайн»**

- Файл: `backend/src/modules/recognition.py`:44
- Последствие: Ответ на прямой вопрос заказчика «откуда берётся online/offline»: авто-механизма определения offline НЕТ. Как только камера один раз прислала событие или прошла /check, она навсегда «онлайн». Если камеру выключат/отвяжут кабель или CV-контейнер перезапустится (StreamManager держит потоки только в памяти self._streams, при рестарте они теряются, а backend их не перезапускает и статус ONLINE не гасит) — на дашборде по-прежнему «камер онлайн: N», хотя распознавания нет. Оператор не увидит, что КПП ослеп.
- Воспроизведение: 1) POST /api/v1/hikvision/anpr-event от зарегистрированной камеры → её status становится online, last_seen_at=now. 2) Больше событий не слать, /check не вызывать. 3) GET /api/v1/dashboard/stats и GET /api/v1/cameras спустя любое время → status по-прежнему 'online'. Ничто и никогда не переведёт её в offline автоматически.
- Фикс: Вычислять статус из last_seen_at на лету (online, если now-last_seen_at < порога, иначе offline) либо добавить периодическую задачу (worker/scheduler), которая проставляет OFFLINE камерам с устаревшим last_seen_at. Сейчас поле last_seen_at собирается вхолостую.

### [42] HIGH · CONFIRMED · camera-onboarding
**Пароль камеры утекает наружу через ручной stream_url: CameraOut отдаёт его сырым, маскирование обходится, а эндпоинты /cameras без авторизации**

- Файл: `backend/src/schemas.py`:179
- Последствие: Заявленный инвариант нарушен: и модель (models.py:224 «Пароль наружу не отдаём»), и сама страница обещают «в браузер пароль не попадает» (CamerasPage.tsx:138-140). Но если оператор вписал rtsp://admin:pass@ip в поле stream_url (штатный сценарий для нестандартных источников), пароль в открытом виде возвращается в обоих полях ответа GET /cameras, а эндпоинт публичный — любой в сети читает учётки камер без логина.
- Воспроизведение: 1) POST /api/v1/cameras {name, stream_url:'rtsp://admin:Secret123@192.168.8.30:554/Streaming/Channels/102'}. 2) curl http://localhost:8001/api/v1/cameras БЕЗ Authorization → 200, в JSON stream_url и stream_url_display содержат 'admin:Secret123' открытым текстом.
- Фикс: Не возвращать сырой stream_url в CameraOut (или маскировать учётку и в нём тоже — вынести маскирование из ветки сборки в общий постпроцесс), и закрыть роутер /cameras авторизацией (Depends(get_current_user)/require_role), как сделано для /users и /access-entries.

### [43] HIGH · CONFIRMED · tests-ci-config
**CI ни разу не запускает Alembic: схема в тестах строится create_all по SQLite, а объявленные в CI postgres/redis и DATABASE_URL/REDIS_URL не используются вообще**

- Файл: `.github/workflows/ci-cd.yml`:101
- Последствие: Битая миграция, расхождение модель<->миграция, вторая голова после мержа двух веток и любые Postgres-специфичные отказы (типы, NOT NULL без server_default на непустой таблице, FK) проходят зелёный CI и падают только на `alembic upgrade head` в контейнере при деплое — с уже остановленным старым бэкендом. Сервисы postgres/redis в CI создают ложное впечатление, что БД тестируется.
- Воспроизведение: grep -n 'alembic' .github/workflows/ci-cd.yml -> пусто. В conftest.py БД = sqlite+aiosqlite:///:memory: + create_all. Прогон `docker run --rm -v $PWD:/w -w /w -e POSTGRES_PASSWORD=test -e MINIO_ROOT_PASSWORD=test smart-parking-backend pytest -q` -> «113 passed» без единого обращения к Postgres.
- Фикс: В backend-job добавить шаги против сервиса postgres: `alembic upgrade head`, `alembic downgrade -1 && alembic upgrade head` (проверка обратимости), `test $(alembic heads | wc -l) -eq 1` и `alembic check` (autogenerate-дрейф). Хотя бы часть интеграционных тестов гонять на реальном Postgres (фикстура, читающая POSTGRES_* из env), а не только на SQLite; в sqlite-фикстуре включить `PRAGMA foreign_keys=ON`. Убрать неиспользуемые DATABASE_URL/REDIS_URL из CI или завести под них поля в Settings; снять continue-on-error с mypy или явно зафиксировать, что strict пока не обязателен.

### [44] HIGH · CONFIRMED · tests-ci-config
**/health отдаёт 200 даже когда БД недоступна — HEALTHCHECK контейнера никогда не краснеет, depends_on: service_healthy бесполезен**

- Файл: `backend/src/main.py`:81
- Последствие: Бэкенд с оборванным коннектом к Postgres вечно числится healthy: restart-политика его не перезапустит, оркестратор не выведет из балансировки, фронт стартует и показывает пустые экраны/500 вместо честного отказа. Отдельно: пул SQLAlchemy сам по себе не восстановится, а сигнала о деградации никто не получит. Тестов на /health нет ни одного (grep 'health' tests/ -> пусто), эндпоинт не подключён ни к одной тестовой сборке app.
- Воспроизведение: 1) docker compose ps -> parking_backend (healthy); 2) curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/health -> 200; 3) по коду main.py:90 та же 200 вернётся и при db_ok=False (например при `docker compose stop postgres`) — контейнер останется healthy.
- Фикс: Возвращать 503 при db_ok=False (`JSONResponse(status_code=503, ...)` либо `Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)`), развести /health (liveness, всегда 200) и /ready (readiness, 503 при недоступной БД/MinIO) и указать в HEALTHCHECK именно /ready. Добавить тест: при подменённом engine, кидающем исключение, /health -> 503.

### [45] HIGH · CONFIRMED · tests-ci-config
**Продовый образ фронтенда — это Vite dev-сервер, собранный npm install мимо лок-файла, и именно он пушится в GHCR как релиз**

- Файл: `frontend/Dockerfile`:1
- Последствие: В прод уезжает дев-сервер: неминифицированный исходный код и sourcemaps наружу, HMR-websocket, отсутствие кеш-хедеров и gzip, потребление памяти на трансформацию каждого запроса, и невоспроизводимая сборка зависимостей (риск supply-chain). Плюс ловушка при будущем переходе на production-build: VITE_API_URL из compose перестанет применяться, фронт пойдёт на дефолтный адрес.
- Воспроизведение: cat frontend/Dockerfile (см. выше) + .github/workflows/ci-cd.yml matrix -> service: frontend, context: ./frontend, push: true. Локально: `docker compose ps` -> parking_frontend ... "docker-entrypoint.s…" на порту 5173, т.е. dev-сервер.
- Фикс: Сделать multi-stage Dockerfile: builder (`npm ci` + `npm run build`, VITE_API_URL/VITE_CV_URL через ARG) -> runtime на nginx:alpine с готовым dist и SPA-fallback. Если адрес API обязан задаваться в рантайме — генерировать /config.json (или window.__ENV__) энтрипоинтом nginx и читать его в клиенте, а VITE_API_URL из compose тогда убрать, чтобы он не выглядел рабочим. Отдельный dev-образ (текущий) оставить только для docker-compose.override.yml и не пушить в GHCR.

### [46] HIGH · PLAUSIBLE · camera-onboarding
**Направление камеры (entry/exit) не участвует в приёме push-событий Hikvision — правильно заведённая камера всё равно даёт UNKNOWN и сессия не создаётся**

- Файл: `backend/src/modules/recognition.py`:123
- Последствие: Заказчик заводит камеру, честно проставляет ей «Въезд», но каждое реальное событие Hikvision, в котором нет распознаваемого поля направления (а в базовой ANPR-нотификации его обычно нет — направление это топология, а не свойство события), падает в UNKNOWN → парковочная сессия НЕ открывается и НЕ закрывается, всё уходит в ручную проверку. То есть основной сквозной сценарий «камера завелась → машина заезжает → сессия создалась» не работает для прямого проезда, хотя направление у камеры задано.
- Воспроизведение: 1) Завести камеру name='IPCamera 01', direction='entry'. 2) curl -X POST http://localhost:8001/api/v1/hikvision/anpr-event -H 'Content-Type: application/xml' с EventNotificationAlert, где есть <channelName>IPCamera 01</channelName> и <licensePlate>, но НЕТ <direction>. 3) Ответ: session_action='ignored', событие помечено unknown_direction, сессия не создана — несмотря на camera.direction='entry'.
- Фикс: В receive_anpr_event после _resolve_camera_id, если event.direction==UNKNOWN и у найденной камеры задан camera.direction, подставлять направление из карточки камеры (camera.direction.upper()) перед вызовом handle_recognition_event. Тогда Camera.direction станет единым источником направления и для RTSP, и для push-событий.

### [47] HIGH · PLAUSIBLE · полнота
**Решение о шлагбауме нигде физически не исполняется — система только пишет в лог «шлагбаум открыт/закрыт», но не отдаёт команду на железо**

- Файл: `backend/src/modules/session.py`:506
- Последствие: Вся серверная логика доступа (красный список, блок выезда при недоплате, зелёный/жёлтый) и оплаты — чисто консультативная: физический шлагбаум никогда не получает от системы команду открыть/держать закрытым. На объекте в Акколе машина из красного списка проедет, а неоплаченная выедет, если шлагбаум не завязан на систему; а если завязан — открывать его нечем. Это и есть заявленная ТЗ §6.2 функция, которая не работает.
- Воспроизведение: 1) POST /api/v1/hikvision/anpr-event с номером из красного списка → ответ session_action=access_denied_red, в БД Alert, в логах «шлагбаум закрыт», но ни одного исходящего запроса к шлагбауму/реле/камере нет (проверяется отсутствием кода и сетевой активности). 2) grep -rniE 'relay|gpio|/ISAPI|open.?gate|barrier' по backend/cv/frontend/src → только строки логов и доки, вызовов нет.
- Фикс: Ввести драйвер актуатора шлагбаума (Hikvision ISAPI зона тревоги/реле, либо GPIO/Modbus-контроллер), конфиг команды открытия на модели Gate, и вызывать его из handle_recognition_event на исходах closed/access_denied_red/exit_denied_unpaid. Либо явно задокументировать, что барьером управляет камера по своему allowlist — но тогда серверные красный список и блок недоплаты бессмысленны.

### [48] HIGH · PLAUSIBLE · полнота
**Порог уверенности CV (0.5) и бэкенда (0.85) не согласованы — распознанные машины в полосе 0.50–0.85 молча не создают сессию и не открывают шлагбаум**

- Файл: `backend/src/config.py`:51
- Последствие: CV в проде запущен с порогом 0.5 и считает номер распознанным (events_emitted растёт, в ленте «успех»), а бэкенд молча выбрасывает всё <0.85 в ручную проверку без сессии и без открытия шлагбаума. На реальных камерах fast-plate-ocr регулярно выдаёт 0.6–0.8 → целый диапазон легитимных машин застревает на въезде/выезде, оператор видит рост очереди low_confidence при «нормальном» распознавании.
- Воспроизведение: curl -X POST http://localhost:8001/api/v1/hikvision/anpr-event -H 'Content-Type: application/json' -d '{"plateNumber":"CONF070KZ","direction":"entry","confidence":70,"channelName":"probe-cam"}' → session_action=low_confidence, сессии нет. Тот же запрос с confidence=90 → session_action=created.
- Фикс: Держать единый порог: либо поднять CV_CONFIDENCE до recognition_min_confidence (и передавать один источник истины), либо выровнять оба на значение ТЗ §2.4 (0.85) и в CV не эмитить события ниже порога, чтобы «распознано» в CV и «принято» в бэкенде значили одно и то же.

### [49] HIGH · PLAUSIBLE · полнота
**Недоступность MinIO роняет весь приём ANPR-события в 500: узкий except S3Error не ловит ошибки соединения, а фото грузятся ДО записи события**

- Файл: `backend/src/storage.py`:81
- Последствие: Любой сбой/недоступность/misconfig MinIO превращает каждый реальный multipart-пуш Hikvision (он всегда несёт картинки) в 500: событие даже не записывается в БД, сессия/шлагбаум не обрабатываются. В связке с отсутствием ретраев в CV-синке (уже найдено) проезд теряется безвозвратно. То есть внешнее хранилище фото становится единой точкой отказа всего учёта въездов/выездов.
- Воспроизведение: В контейнере backend: from minio import Minio; Minio('127.0.0.1:9001',...).put_object('parking-plates','o',io.BytesIO(b'12345'),5,'image/jpeg') → urllib3.exceptions.MaxRetryError, не пойман except S3Error. Значит при остановленном/недоступном MinIO POST multipart-события с фото вернёт 500 и не создаст ни событие, ни сессию.
- Фикс: В storage.upload/ensure_bucket ловить широкий Exception (или (S3Error, urllib3.exceptions.HTTPError, ValueError, OSError)) и возвращать None; дополнительно обернуть блок загрузки фото в recognition.py в try/except, чтобы отказ хранилища деградировал до «событие без фото», а не ронял приём проезда.

### [50] HIGH · PLAUSIBLE · полнота
**Нет инварианта «один активный тариф»: одновременно активны несколько, get_active_tariff берёт max(id), создание тарифа молча перебивает тариф; при выключении всех — парковка бесплатна**

- Файл: `backend/src/modules/tariff.py`:61
- Последствие: Ставка списания недетерминирована с точки зрения оператора: создание второго тарифа (напр. «ночной») мгновенно и молча делает активным его (max id), не выключая прежний; правка «не того» активного тарифа не влияет на деньги. А если оператор снимет is_active со всех, чтобы отредактировать, get_active_tariff→None→tariff_price=0 → КАЖДАЯ машина выезжает бесплатно, без ошибки, без UNPAID и без алерта. На первом же реальном заведении тарифов это даёт неверные или нулевые списания.
- Воспроизведение: GET /api/v1/tariffs (или SELECT id,is_active,price_per_hour FROM tariff) на стенде → id1/id3/id6 все active. Провести EXIT платной сессии → цена считается по id6 (123/ч), а не по «Стд» 200/ч. Выключить все is_active → следующий EXIT закрывается как paid при price=0.
- Фикс: Гарантировать единственный активный тариф: частичный уникальный индекс (unique where is_active) + в create/update снимать is_active с прочих в одной транзакции; при отсутствии активного тарифа — не выпускать бесплатно, а возвращать явную ошибку/алерт «тариф не настроен».

### [51] MEDIUM · CONFIRMED · billing-tariff
**Статус UNPAID не проставляется нигде в коде: список долгов и KPI «Неоплаченные» на дашборде всегда пустые**

- Файл: `backend/src/modules/session.py`:669
- Последствие: Ручка /api/v1/parking-sessions/unpaid и фильтр «Выехал» — недостижимый код: вернуть непустой результат они не могут. Плитка «Неоплаченные» на дашборде постоянно показывает 0, создавая у заказчика ложное впечатление, что долгов нет. При этом настоящие должники (машины, которым отказали в выезде) остаются в статусе active и визуально не отличаются от нормально стоящих машин — у оператора вообще нет списка долгов.
- Воспроизведение: grep -rn "UNPAID" --include="*.py" backend/src/   → присваиваний нет
curl -s :8001/api/v1/parking-sessions/unpaid → []
curl -s :8001/api/v1/dashboard/billing → "unpaid_count":0
psql: select id,status,price,paid_amount from parking_session where status='active' and price>paid_amount; → есть строки (id=23)
- Фикс: Определиться с семантикой долга и реализовать её в одном месте: либо в _handle_exit при отказе (session.py:505) переводить сессию в отдельный статус долга (или добавить флаг has_debt/ debt_amount), либо считать unpaid_count и /parking-sessions/unpaid по условию «status=active AND price > paid_amount», а не по никогда не выставляемому статусу. Плюс тест, который после exit_denied_unpaid ждёт непустой список долгов.

### [52] MEDIUM · CONFIRMED · billing-tariff
**Нет идемпотентности при создании платежа: на одну сессию плодятся платежи на полную сумму долга → двойное списание без возврата**

- Файл: `backend/src/modules/payment.py`:62
- Последствие: Водитель, обновивший страницу оплаты или нажавший «Оплатить» с двух устройств (и/или оператор, продублировавший оплату из Студии), платит дважды за одну стоянку. Переплата ниоткуда не возвращается: на выезде due = price - paid_amount уходит в минус, сессия закрывается как paid, лишние деньги остаются на paid_amount и в revenue_today. Механизма refund в системе нет вообще.
- Воспроизведение: curl -s -X POST :8001/api/v1/payments/create -d '{"session_id":25}'   → amount 800, provider_payment_id A
curl -s -X POST :8001/api/v1/payments/create -d '{"session_id":25}'   → amount 800, provider_payment_id B (второй платёж на ту же сумму)
Подтвердить оба webhook'ом → psql: select paid_amount from parking_session where id=25; → 1600 при долге 800
- Фикс: В create_payment_for_session сначала искать по сессии живой PENDING-платёж и переиспользовать его (или отменять устаревший и создавать новый), а amount_due считать с учётом ещё не подтверждённых pending-сумм. Дополнительно: в credit_session (payment.py:84-97) ограничивать зачисление остатком долга либо явно фиксировать переплату отдельным полем/статусом refund_pending, чтобы её было видно и можно было вернуть.

### [53] MEDIUM · CONFIRMED · auth-security
**Аудит покрывает только 5 действий: вход в систему, ручная отмена сессии, назначение направления, правки тарифов/шлагбаумов/камер и подтверждение оплат не логируются вообще**

- Файл: `backend/src/modules/auth.py`:114
- Последствие: Требование ТЗ «действия с привязкой к личности» выполнено только для управления пользователями и списками. Расследовать инциденты нельзя: кто выпустил машину, кто отменил сессию, кто поменял тариф, кто подтвердил оплату и кто вообще входил в систему — в журнале отсутствует. Усугубляется находкой №1: у этих ручек нет даже аутентификации, поэтому пользователя для записи взять неоткуда.
- Воспроизведение: grep -rn 'record_audit' src/ | grep -v 'def record_audit'  -> 5 вызовов только в user.py и access.py; затем docker compose exec -T postgres psql -U parking_user -d parking_db -c "select distinct action from audit_log;" -> только access.create и user.create после логинов, отмен сессий и оплат на стенде.
- Фикс: После закрытия ручек аутентификацией добавить record_audit в: login (успех/провал), cancel_session, assign_event_direction, ack_alert, CRUD тарифов/шлагбаумов/камер, ручное подтверждение оплаты и вызовы Kaspi. Действия, влияющие на деньги и проезд, писать с entity/entity_id и суммой, чтобы аудит был пригоден для разбора.

### [54] MEDIUM · CONFIRMED · access-lists
**valid_until из формы уходит без таймзоны и сохраняется как UTC — жёлтое окно сдвигается на 5 часов, а таблица показывает не то время, что ввёл оператор**

- Файл: `frontend/src/pages/AccessListsPage.tsx`:87
- Последствие: Оператор задаёт «бесплатно до 18:00», фактически бесплатный период заканчивается в 23:00 по местному времени — 5 лишних бесплатных часов на каждую жёлтую запись (недобор выручки), а при обратной ситуации (сервер/клиент в другой зоне) — преждевременное начисление. Внутри одной страницы значения расходятся: в форме редактирования показывается 18:00 (startEdit, AccessListsPage.tsx:75 — .slice(0,16) от строки с Z), в таблице — 23:00. Ошибка бесшумная, обнаруживается только по жалобе клиента.
- Воспроизведение: 1) Открыть Списки доступа, добавить жёлтую запись, в «Бесплатно до» выбрать 23.07.2026 18:00;
2) curl -s localhost:8001/api/v1/access-entries -H 'Authorization: Bearer <t>' → "valid_until":"2026-07-23T18:00:00Z";
3) В таблице на странице (браузер в Asia/Almaty) та же запись отображается как 23:00:00 23.07.2026.
- Фикс: На фронте конвертировать значение datetime-local в ISO со смещением перед отправкой (new Date(form.valid_until).toISOString()) и обратно — в локальную строку для input (учитывая getTimezoneOffset), вместо .slice(0,16). На бэке в схемах добавить валидатор, который отвергает naive datetime (или явно доопределяет его в таймзоне парковки), чтобы контракт не зависел от формата клиента.

### [55] MEDIUM · CONFIRMED · access-lists
**Алерты красного списка не дедуплицируются: каждое событие камеры создаёт новую запись, лента limit(100) вытесняет реальные сигналы**

- Файл: `backend/src/modules/access.py`:72
- Последствие: Реальная камера Hikvision отдаёт несколько ANPR-событий за один подъезд, а стоящая перед закрытым шлагбаумом машина из красного списка — десятки. Каждое даёт отдельный Alert, баннер «Красный список — сигнал» на странице (опрос каждые 8 с) забивается идентичными строками, и оператор должен кликать «принято» по каждой. Хуже: list_alerts (access.py:182) отдаёт `order_by(created_at desc).limit(100)`, поэтому при потоке дублей от одной машины другие, действительно новые неподтверждённые сигналы вытесняются за пределы выборки и пропадают с экрана ответственного — сигнал теряется. Плюс неограниченный рост таблицы alert от одной машины.
- Воспроизведение: for i in 1..6: curl -X POST localhost:8001/api/v1/hikvision/anpr-event -d '{"licensePlate":"666RED66","direction":"in","dateTime":"2026-07-22T10:00:0$i+00:00","confidenceLevel":99}'
docker compose exec -T postgres psql -U parking_user -d parking_db -c "select plate, count(*) from alert group by plate;" → 666RED66 | 7
- Фикс: В record_alert перед вставкой искать неподтверждённый Alert того же kind/plate/gate_id, созданный в пределах окна (например settings.entry_restart_window_seconds или 5 минут): если есть — обновлять created_at/счётчик повторов вместо новой строки. Дополнительно снять limit(100) в пользу пагинации либо сортировать неподтверждённые так, чтобы старые не выпадали, и записывать ack в аудит (сейчас ack_alert, access.py:189-197, доступен любому аутентифицированному и не оставляет следа в AuditLog).

### [56] MEDIUM · CONFIRMED · kaspi-payments
**Ссылка/QR Kaspi формируется с account=«session-N», а входящий протокол ищет account как госномер — оплата по этой ссылке всегда вернёт result=1 (и такие платежи никогда не сходятся)**

- Файл: `backend/src/modules/payment.py`:69
- Последствие: Ветка payment_provider=kaspi нерабочая end-to-end: сгенерированный приложением QR/deeplink ведёт на несуществующий «абонентский счёт», Kaspi отвечает «абонент не найден»; в БД копятся вечно-pending kaspi-платежи, дублирующие реальные. Плюс опечатка в PAYMENT_PROVIDER на проде тихо включает mock-провайдера, «оплата» которого подтверждается открытым webhook'ом (см. находку №1).
- Воспроизведение: 1) Задать kaspi_pay_deeplink_template и payment_provider=kaspi, POST /api/v1/payments/create -> pay_url содержит account=session-<id>. 2) Дёрнуть GET /api/kaspi/pay?command=check&account=session-<id>&txn_id=1 (при kaspi_provider_enabled=true) -> result=1 (NOT_FOUND), потому что kaspi.py:100 приводит account к номеру авто. 3) Тот же check по plate_number возвращает result=0 — подтверждает расхождение контракта.
- Фикс: Передавать в provider.create reference=parking.plate_number (account в протоколе Kaspi = номер авто) либо научить _handle_check/_handle_pay резолвить account и как «session-N», и как номер. Платёж, созданный провайдером, связывать с входящим pay (по session_id) вместо создания второй записи. Значение payment_provider валидировать на старте (Literal["mock","kaspi"]) и запрещать mock при app_env=prod.

### [57] MEDIUM · CONFIRMED · db-migrations
**normalize_plate вырезает всё, кроме [A-Z0-9] — кириллические номера-гомоглифы молча калечатся; в живой БД уже лежат «мёртвые» записи красного списка ('' и '55502')**

- Файл: `backend/src/modules/access.py`:41
- Последствие: Казахстанские номера набирают визуально неотличимыми кириллическими А, В, Е, К, М, Н, О, Р, С, Т, У, Х. Оператор вводит «555 АВС 02» кириллицей, система молча сохраняет «55502» (или '' при полностью кириллическом вводе), в UI номер отображается искажённым, а resolve_access никогда не совпадёт с латинским выводом OCR «555ABC02». Красный список тихо не срабатывает — машина из запрета проезжает как обычная, алерт не создаётся. Ошибка не диагностируется: API возвращает 201, аудит пишется.
- Воспроизведение: 1) psql: select id, plate, list_type from access_entry where plate='' or plate='55502';  → две red-записи, обе никогда не матчатся.
2) python3 -c "import re; print(repr(re.sub(r'[^A-Z0-9]','', '555АВС02'.upper())))"  (буквы кириллические) → '55502'.
3) Событие с латинским номером: POST /api/v1/hikvision/anpr-event {"licensePlate":"555ABC02",...} → session_action=created, флаг access_denied_red не выставлен, alert не создан.
- Фикс: Транслитерировать кириллические гомоглифы перед вырезанием (А→A, В→B, Е→E, К→K, М→M, Н→H, О→O, Р→P, С→C, Т→T, У→Y, Х→X), затем чистить; в create_entry/update_entry после нормализации проверять `if not plate: raise HTTPException(400, "Номер пустой после нормализации")`. В БД добавить `CHECK (length(plate) > 0)` и уникальность `UNIQUE (plate, gate_id, list_type)` (частичный индекс с coalesce(gate_id,-1)), чтобы дубли и пустышки не заводились.

### [58] MEDIUM · CONFIRMED · db-migrations
**Модели ≠ миграции: составной индекс ix_parking_session_plate_status есть только в миграции, `alembic check` падает, следующий autogenerate его дропнет; миграции вообще не прогоняются в тестах**

- Файл: `backend/migrations/versions/0002_parking_session.py`:72
- Последствие: Первый же `alembic revision --autogenerate` сгенерирует drop_index для ix_parking_session_plate_status и на проде удалит индекс, обслуживающий самый горячий запрос ANPR-конвейера — `_find_active_at_gate` (session.py:96-109, WHERE plate_number=? AND status='active'), который выполняется на КАЖДОЕ событие камеры. После этого каждый проезд будет вызывать seq scan по parking_session. Плюс `alembic check` уже красный, т.е. любой будущий дрейф моделей и миграций в этом проекте не детектируется.
- Воспроизведение: docker compose exec -T backend sh -c 'cd /app && alembic check'
→ FAILED: New upgrade operations detected: [('remove_index', Index('ix_parking_session_plate_status', ...))]
(головной ревизии одна: `alembic heads` → 0010_access_lists (head); alembic_version в БД = 0010_access_lists — с этим всё в порядке)
- Фикс: Объявить индекс в модели: у ParkingSession добавить `__table_args__ = (Index("ix_parking_session_plate_status", "plate_number", "status"),)` — тогда autogenerate перестанет его удалять. Дополнительно: завести в CI шаг `alembic upgrade head && alembic check && alembic downgrade base` на настоящем Postgres-контейнере (сейчас все тесты идут на sqlite через create_all, так что миграции не проверены ни разу).

### [59] MEDIUM · CONFIRMED · cv-service
**Фильтр качества кадра (ТЗ 2.1, blur/dark) не применяется в живом потоке — работает только в офлайновом run_video**

- Файл: `cv/recognizer/stream.py`:65
- Последствие: Заявленный в ТЗ и сконфигурированный отсев смазанных и тёмных кадров в проде мёртв. Ночью/в дождь смазанные кадры уходят в OCR и их мусорные чтения попадают в MajorityVote наравне с хорошими: при нескольких смазанных кадрах против пары чётких голосование выбирает неверный номер (MajorityVote.result ранжирует прежде всего по количеству голосов, vote.py:39-42), и в бэкенд уходит событие с чужим/битым номером. На живом стенде такие мусорные чтения уже наблюдались: событие с plate="I752LLG" (не формат KZ). Плюс лишняя нагрузка на OCR по заведомо негодным кадрам.
- Воспроизведение: grep -rn 'frame_ok' cv/ -> только quality.py, pipeline.py:137 и tests/test_quality.py; ни одного вхождения в recognizer/stream.py, через который идёт весь живой поток (service.py:172). Практически: подать в /stream/start заведомо смазанный/тёмный RTSP — frames_seen в /stream/status растёт, кадры обрабатываются, отсева нет.
- Фикс: В StreamPipeline.process перед вызовом process_frame добавить тот же гейт, что в run_video: `if not frame_ok(frame.image, self.cfg.blur_threshold, self.cfg.dark_threshold): self.tracker.update([]); return self._collect_closed()` — важно при этом всё равно старить треки (иначе max_age начнёт считаться по годным кадрам и две машины через серию плохих кадров сольются в один трек). Завести счётчик отброшенных по качеству кадров и отдавать его в /stream/status, плюс тест на отсев в tests/test_stream_emission.py.

### [60] MEDIUM · CONFIRMED · frontend-correctness
**Фронт и бэк выбирают разный «активный тариф»: показанная сумма не совпадает со списанной**

- Файл: `frontend/src/pages/StudioPage.tsx`:126
- Последствие: Как только активных тарифов становится больше одного, водитель на /pay/:id и оператор в Студии видят сумму по одному тарифу, а бэкенд при POST /api/v1/payments/create считает due по другому (modules/payment.py:49-72 через get_active_tariff) и спишет иную сумму. В крайнем случае фронт показывает «Долга нет — можно выезжать ✓» (PaymentPage.tsx:52 `due <= 0`), а шлагбаум на выезде остаётся закрыт с exit_denied_unpaid, потому что серверный тариф насчитал долг. KPI «Активный тариф» на /tariffs при этом называет не тот тариф, по которому реально считаются деньги.
- Воспроизведение: 1) /tariffs → создать тариф «Ночной», цена за час 1000, галка «Активный тариф» стоит по умолчанию → в системе два активных (id=1 «Стд» 200 ₸/ч и новый с бо́льшим id).
2) Эмулировать въезд машины на 3 часа (Студия → «Стоит уже» 180 мин → Въезд).
3) Открыть /pay/{session_id}: фронт покажет 600 ₸ (тариф с минимальным id). Нажать «Оплатить» → в БД создастся Payment на 3000 ₸ (`GET /api/v1/payments/status/{id}` / SELECT amount FROM payments) — по тарифу с максимальным id.
- Фикс: Привести выбор к одному правилу и убрать возможность рассинхрона: во фронте выбирать так же, как бэкенд — `[...(tariffs.data ?? [])].reverse().find((t) => t.is_active)` (или сортировать по id desc), и вынести это в один хелпер `pickActiveTariff()` вместо трёх копий find() в StudioPage/PaymentPage/TariffsPage. Параллельно на бэке сделать активность эксклюзивной (в create_tariff/update_tariff при is_active=true снимать флаг у остальных) либо добавить частичный уникальный индекс `CREATE UNIQUE INDEX ... ON tariffs (is_active) WHERE is_active` — тогда неоднозначности не будет в принципе.

### [61] MEDIUM · CONFIRMED · frontend-correctness
**StreamPanel не останавливает поток CV при уходе со страницы — сервис продолжает лить фейковые проезды в боевую базу**

- Файл: `frontend/src/pages/StreamPanel.tsx`:114
- Последствие: Оператор запускает поток на вкладке «Тест CV» и уходит на другую страницу/закрывает вкладку — CV-сервис продолжает крутить видео и бесконечно POST-ить события в боевой backend, порождая мусорные сессии и события, накручивая «Событий сегодня», «Сейчас на парковке» и статистику. Из UI это не остановить: вернувшись, оператор видит `active=false` и кнопку «Старт», а не «Стоп»; единственный способ — дернуть POST /stream/stop руками или перезапустить сервис. Дополнительно при подтормаживании CV лента событий показывает дубли одного проезда, из-за чего оператор может решить, что машина проехала дважды.
- Воспроизведение: 1) /studio → вкладка «Тест CV» → URL `demo` → «▶ Старт». В ленте пошли события, в /active растут машины.
2) Не нажимая «Стоп», переключиться на вкладку «Эмуляция КПП» (или уйти на /sessions) — StreamPanel размонтируется.
3) `curl -s http://localhost:8090/stream/status` → `"running": true`, счётчики frames/events продолжают расти; `curl -s -H "Authorization: Bearer $T" "http://localhost:8001/api/v1/recognition/events?limit=1"` → total продолжает увеличиваться сам по себе.
4) Вернуться на вкладку «Тест CV» — UI показывает «поток не запущен» и кнопку «▶ Старт».
- Фикс: 1) В cleanup эффекта останавливать поток: `return () => { alive = false; clearInterval(id); void stopStream(CAMERA); }` (или отдельным эффектом с пустыми deps), плюс `window.addEventListener("beforeunload", () => navigator.sendBeacon(...))` для закрытия вкладки. 2) На монтировании один раз опрашивать `getStreamStatus()` без условия `active` и восстанавливать `setActive(mine?.running ?? false)`, чтобы UI подхватывал уже работающий поток и давал его остановить. 3) Убрать гонку: заменить setInterval на самопланирующийся цикл (`await tick(); if (alive) timer = setTimeout(loop, 1000)`) либо ввести флаг `inFlight`, чтобы новый tick не стартовал, пока предыдущий не завершился.

### [62] MEDIUM · CONFIRMED · camera-onboarding
**Приём ANPR-событий полностью открыт (без авторизации, без IP-allowlist, без требования регистрации камеры) — инъекция/реплей событий даёт бесплатную парковку и «призрачные» сессии**

- Файл: `backend/src/modules/recognition.py`:88
- Последствие: Ответ на «что будет при событии от неизвестной камеры»: событие молча принимается и создаёт сессию в зоне gate_id=NULL (без шлагбаума, доступ резолвится только по глобальным спискам) — учёт по зонам ломается. Хуже: так как эндпоинт открыт, кто угодно в сети, зная номер, шлёт ENTRY каждые <10 минут и постоянно сдвигает старт сессии на «сейчас» → amount_due всегда ~0, машина стоит бесплатно. Плюс можно засорять БД поддельными номерами/сессиями.
- Воспроизведение: curl -X POST http://localhost:8001/api/v1/hikvision/anpr-event -H 'Content-Type: application/json' -d '{"plateNumber":"777XYZ02","direction":"forward","dateTime":"..."}' повторять с растущим временем в пределах 600 c — каждый ответ 'entry_restarted', entry_time сессии двигается вперёд; итоговая цена не накапливается.
- Фикс: Закрыть /hikvision/anpr-event: mTLS/секретный токен от камеры или IP-allowlist (как у kaspi), опционально отклонять/помечать события от неизвестных камер. Ограничить сдвиг entry_adjusted, чтобы серия ENTRY не могла бесконечно обнулять оплачиваемое время.

### [63] MEDIUM · CONFIRMED · camera-onboarding
**event_time берётся из полезной нагрузки камеры без валидации — сбитые/будущие часы камеры дают отрицательный parked_seconds и вечно бесплатную сессию**

- Файл: `backend/src/modules/recognition.py`:123
- Последствие: Камера с неверными часами — рядовая эксплуатационная ситуация, особенно при заведении новой Hikvision. Если её время убежало вперёд, каждая сессия этой камеры получает entry_time из будущего → к оплате всегда 0 (бесплатный проезд) и отрицательная длительность, которая уже сейчас утекает в API/на фронт (parked_seconds:-108742535). Наивное время (без tz) молча трактуется как UTC — при часовом поясе KZ (+5/+6) это ещё и systematically смещает счёт.
- Воспроизведение: curl -X POST http://localhost:8001/api/v1/hikvision/anpr-event -H 'Content-Type: application/json' -d '{"plateNumber":"FUTURE01","direction":"forward","dateTime":"2030-01-01T00:00:00+00:00"}' → сессия создана; GET /api/v1/parking-sessions/<id> → parked_seconds отрицательный, price=null; при выезде к оплате будет 0.
- Фикс: Валидировать event_time на приёме: отклонять/зажимать время сильно в будущем и подозрительно старое (clamp к now или флаг ручной проверки), а наивные метки приводить к таймзоне стенда явно, а не молча к UTC.

### [64] MEDIUM · CONFIRMED · camera-onboarding
**Хрупкая привязка события к камере: сопоставление по точному совпадению channelName с Camera.name/ip, без нормализации и без уникальности имени**

- Файл: `backend/src/modules/recognition.py`:24
- Последствие: Чтобы событие боевой Hikvision привязалось к камере (а значит — к шлагбауму, зоне, спискам доступа и обновлению last_seen), имя камеры в карточке ДОЛЖНО в точности совпасть с channelName, который камера шлёт (лишний пробел/регистр/'IPCamera 01' vs 'Entry-Cam-1' — мимо). При промахе camera_id=NULL → сессия без шлагбаума, доступ только по глобальным спискам, статус камеры не обновляется. Если две камеры названы одинаково, .first() выберет произвольную → событие уедет в чужую зону. Заказчик, спрашивающий «как камера привязывается к шлагбауму», об этом требовании нигде не предупреждён.
- Воспроизведение: Завести камеру name='Entry-Cam-1', gate_id=1. Прислать событие Hikvision, где channelName='IPCamera 01' (заводское имя канала). _resolve_camera_id → None → сессия с gate_id=NULL, last_seen камеры не обновлён, хотя камера зарегистрирована.
- Фикс: Нормализовать сопоставление (trim/casefold), дать явное поле-идентификатор канала (напр. channel_key) вместо перегрузки name, добавить UNIQUE на ключ сопоставления и при неоднозначности/промахе явно логировать и помечать событие, а не молча ронять привязку.

### [65] MEDIUM · PLAUSIBLE · kaspi-payments
**Автосписание Kaspi блокирует решение шлагбаума: синхронный HTTP-вызов внутри обработки ANPR-события, до ~45 c на событие, с удержанием соединения/транзакции БД**

- Файл: `backend/src/modules/session.py`:495
- Последствие: При недоступном/медленном autopayments.kaspi.kz машина стоит перед закрытым шлагбаумом десятки секунд на каждое распознавание, камера ретраит событие, соединения из пула БД заняты ожиданием банка — деградация всего приёма событий (в том числе для других шлагбаумов), вплоть до исчерпания пула.
- Воспроизведение: Включить kaspi_autopay_enabled и указать недоступный kaspi_autopay_base_url (или заблокировать порт) -> POST /api/v1/hikvision/anpr-event с direction=EXIT по сессии с долгом отвечает не раньше чем через timeout соединения; при 15.0 по всем фазам httpx худший случай ~45 c. Каждое повторное событие (см. 3 x exit_denied_unpaid) добавляет ещё столько же.
- Фикс: 1) Явный httpx.Timeout(connect=2, read=5, write=5) + общий бюджет через asyncio.wait_for (1-3 c), чтобы решение шлагбаума укладывалось в реальное время подъезда. 2) Вынести списание из синхронного пути ANPR: решение о выпуске принимать по уже известному paid_amount, а автосписание делать фоновой задачей/воркером (worker.py) с последующим повторным EXIT. 3) Не держать транзакцию БД открытой на время внешнего HTTP (закоммитить состояние до вызова).

### [66] MEDIUM · PLAUSIBLE · полнота
**Дашборд и биллинг считают «сегодня» по UTC, а не по Asia/Almaty (UTC+5): выручка/события за день и фильтры по дате сдвинуты на 5 часов**

- Файл: `backend/src/modules/payment.py`:161
- Последствие: «Выручка за сегодня», «событий за сегодня» и фильтры по дате въезда переключаются в 05:00 по Акколе, а не в полночь: вечерняя выручка уезжает в завтра, а всё с 00:00 до 05:00 попадает во вчера. Ежедневные сводки и выгрузки по датам систематически неверны у краёв суток; настройки таймзоны в системе нет.
- Воспроизведение: GET /api/v1/dashboard/billing и /dashboard/stats около местной полуночи — revenue_today/events_today не совпадут с фактическим локальным днём. Платёж в 23:30 местного (18:30Z) 21 июля попадёт в «сегодня» уже 22-го только после 05:00Z, т.е. будет отнесён к неверным суткам.
- Фикс: Считать границы суток в таймзоне объекта (Asia/Almaty, UTC+5) через настраиваемый TZ: вычислять today_start в локальной зоне и конвертировать в UTC для сравнения; те же правки для dashboard_stats и фильтров date_from/date_to в list_sessions.

### [67] MEDIUM · PLAUSIBLE · полнота
**Backend не фильтрует eventType=="ANPR": не-ANPR события (TPSRealTime) сохраняются и засоряют очередь ручной проверки**

- Файл: `backend/src/modules/recognition.py`:120
- Последствие: Каждый TPSRealTime/не-ANPR тик камеры (счётчик трафика, включённый ANR и т.п.) создаёт строку RecognitionEvent с пустым номером. session.handle_recognition_event помечает такие события EventFlag.LOW_CONFIDENCE (session.py:124 `if not event.plate_number: return True` → :256-263), поэтому они падают в очередь ручной проверки и раздувают счётчики событий/дашборд. Прямо противоречит подтверждённому в доке требованию отфильтровывать не-ANPR по eventType.
- Воспроизведение: На живом стенде (endpoint без авторизации): `curl -s -X POST http://localhost:8001/api/v1/hikvision/anpr-event -H 'Content-Type: application/json' -d '{"eventType":"TPSRealTime","plateNo":"unknown","channelName":"Entry_Camera"}'` → ответ `{"status":"ok","id":1667,"plate_number":null,"session_action":"low_confidence"}`. Событие принято (201, присвоен id → строка в БД) и уже помечено low_confidence.
- Фикс: В _read_event/receive_anpr_event извлекать eventType (XML `eventType`, JSON `eventType`) и при значении != 'ANPR' возвращать 200/204 без создания RecognitionEvent (как отвечает 200 сам capture_server), либо парсить plate и молча дропать событие без номера, если тип не ANPR.

### [68] LOW · PLAUSIBLE · полнота
**На странице «Тест распознавания» блок «Также найдено на фото» дублирует основной распознанный номер**

- Файл: `cv/recognizer/pipeline.py`:108
- Последствие: Когда на кадре >1 OCR-кандидата, основной номер повторно показывается в списке «также найдено», что вводит оператора в заблуждение (это не «другие» номера, а тот же). Косметический баг контракта candidates↔UI.
- Воспроизведение: Загрузить на /recognize (вкладка «Тест CV» Студии) фото сцены с текстом, где движок вернёт ≥2 кандидата: распознанный номер отобразится и крупно сверху, и в блоке «Также найдено на фото».
- Фикс: На фронте фильтровать основной номер: показывать `candidates.filter(c => c !== plate_number)` (и по length>0), либо в pipeline._best исключать победителя из alts (`alts = [t[3] for t in scored[1:5] if t[3]]`).
