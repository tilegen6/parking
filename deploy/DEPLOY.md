# Production deploy на Ubuntu 24 VPS (ps.kz) — подробный гайд

Пошаговая инструкция для **первого деплоя**. Рассчитана на новичка: у каждого шага
есть «зачем», точные команды и что должно получиться.

Плейсхолдеры (подставляй свои значения):
- `<IP>` — публичный IP твоего VPS (из панели ps.kz).
- `<domain>` — твой домен, напр. `parking.company.kz`.
- `<github-user>` — твой логин на GitHub.

## Общая картина

Приложение состоит из контейнеров (backend, frontend, Postgres, Redis, MinIO). Ими
управляет `docker compose`. Схема доставки:

```
ты пушишь код в main
   → GitHub Actions собирает Docker-образы backend/frontend
   → кладёт их в GHCR (склад образов GitHub)
   → при DEPLOY_ENABLED=true запускает настроенный deployment
   → ждёт «Approve», если в environment настроены Required reviewers
   → заходит по SSH на VPS: «скачай новые образы и перезапусти»
   → на VPS поднимается стек; наружу открыт только nginx с HTTPS
```

Два конфиг-файла: `docker-compose.yml` (база) + `docker-compose.prod.yml` (прод:
образы из GHCR, nginx+TLS, внутренние порты закрыты). Наружу — только **80/443**.

Порядок работы: **Шаг 0 → 1 → 2 → 3 → 4** (первый запуск руками, проверяем что сайт
открывается) → **Шаг 5** (автодеплой из GitHub). Kaspi (Шаг 7) — в самом конце.

---

## Шаг 0. Домен и DNS

**Зачем:** пользователи и Kaspi заходят по имени, а не по IP. И HTTPS-сертификат
Let's Encrypt выдаётся только на домен (на голый IP — нельзя).

1. В панели своего регистратора домена добавь **A-запись**: `parking` → `<IP>` VPS.
2. Проверь с ноутбука (PowerShell), что домен указывает на сервер:
   ```powershell
   nslookup <domain>
   ```
   В ответе должен быть `<IP>` твоего VPS. DNS обновляется не сразу (до ~часа).

---

## Шаг 1. Сервер: пользователь, ключи, Docker, фаервол

Заходим на сервер под root (пароль/ключ ps.kz прислал на почту при создании VPS):
```powershell
ssh root@<IP>
```
Дальше команды с `#` — выполняются на сервере.

### 1.1. Пользователь `deploy`
**Зачем:** не работать под root (безопаснее). Приложение и деплой идут под `deploy`.
```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
```

### 1.2. SSH-ключ доступа
**Зачем:** вход по ключу вместо пароля. Одну и ту же пару используем и для себя,
и для GitHub Actions (для старта так проще; позже можно развести на два ключа).

Ключ генерируется **на ноутбуке** (не на сервере). В PowerShell:
```powershell
cd ~
ssh-keygen -t ed25519 -f deploy_ci
# на два запроса пароля — просто Enter (у CI-ключа пароля быть не должно)
```
Появятся `deploy_ci` (приватный — секрет) и `deploy_ci.pub` (публичный).

Кладём **публичный** ключ на сервер. Способ А — одной командой с ноутбука
(`tr -d '\r'` убирает Windows-перенос строки, из-за которого ключ часто не работает):
```powershell
Get-Content $HOME\deploy_ci.pub | ssh root@<IP> "mkdir -p /home/deploy/.ssh && tr -d '\r' >> /home/deploy/.ssh/authorized_keys && chown -R deploy:deploy /home/deploy/.ssh && chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys"
```
Способ Б — вручную: `Get-Content $HOME\deploy_ci.pub` (скопировать строку) → на сервере
`nano /home/deploy/.ssh/authorized_keys` (вставить), затем те же `chown`/`chmod`, что выше.

Проверка — зайти под `deploy` этим ключом:
```powershell
ssh -i $HOME\deploy_ci deploy@<IP>
```
Пустило без пароля — успех. `Permission denied (publickey)` — почти всегда права
(нужно `.ssh` = 700, `authorized_keys` = 600) или лишний `\r` (используй Способ А).

Тот же приватный `deploy_ci` пойдёт в GitHub Secret `DEPLOY_SSH_KEY` (Шаг 5).

### 1.3. Docker
**Зачем:** без него нечем запускать контейнеры. Официальный установщик:
```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy      # чтобы deploy запускал docker без sudo
```

### 1.4. Фаервол (ufw)
**Зачем:** закрыть всё лишнее, оставить SSH + веб. Внутренние порты (Postgres и т.д.)
наружу не публикуются вообще.
```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable                     # подтвердить: y
```

### 1.5. (Необязательно, позже) Усиление SSH
Когда убедишься, что заходишь по ключу под `deploy` — можно запретить вход по паролю
и под root в `/etc/ssh/sshd_config` (`PermitRootLogin no`, `PasswordAuthentication no`,
затем `systemctl restart ssh`). **Для первого деплоя пропусти**, чтобы не закрыть себе доступ.

---

## Шаг 2. Проект и секреты на сервере

Переключаемся на `deploy`:
```bash
sudo -iu deploy
```

**Зачем клонировать репозиторий:** на сервере нужны `docker-compose*.yml` и папка
`deploy/` — по ним compose знает, что запускать (код backend/frontend приезжает
готовыми образами из GHCR, собирать его на сервере не нужно).
```bash
git clone https://github.com/tilegen6/parking.git /opt/smart-parking
cd /opt/smart-parking
git checkout main
cp .env.example .env
```

**Зачем `.env`:** пароли и секреты не хранятся в git — они лежат в `.env` на сервере.
Сгенерировать случайную строку: `openssl rand -hex 32`. Заполни:
```bash
nano .env
```
```
APP_ENV=production
DEBUG=false
DOMAIN=<domain>
SERVICE_URL=https://<domain>
CORS_ORIGINS=https://<domain>
MINIO_PUBLIC_URL=https://<domain>/photos
SECRET_KEY=<openssl rand -hex 32>
JWT_SECRET_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=<длинный пароль>
MINIO_ROOT_PASSWORD=<длинный пароль>
GRAFANA_ADMIN_PASSWORD=<длинный пароль>
# Kaspi пока выключен — включим на Шаге 7
PAYMENT_PROVIDER=mock
KASPI_PROVIDER_ENABLED=false
KASPI_AUTOPAY_ENABLED=false
# тег образов; при ручном запуске — latest, при деплое из CI подставится sha-<sha>
IMAGE_TAG=latest
```
Закрыть доступ к файлу: `chmod 640 .env`.

---

## Шаг 3. Доступ к образам GHCR

**Зачем:** образы в GHCR приватные — сервер должен «залогиниться», чтобы их скачивать.

1. На GitHub: **аватар → Settings → Developer settings → Personal access tokens →
   Tokens (classic) → Generate new token**, отметь право **`read:packages`**, создай,
   скопируй токен (`ghp_...`).
2. На сервере под `deploy`:
   ```bash
   echo ghp_ТВОЙ_ТОКЕН | docker login ghcr.io -u <github-user> --password-stdin
   ```
   Ответ `Login Succeeded` — готово (запоминается, повторять не нужно).

---

## Шаг 4. Первый запуск + HTTPS

Короткий псевдоним, чтобы не писать длинную команду каждый раз:
```bash
cd /opt/smart-parking
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup"
```

**Почему в таком порядке:** nginx хочет сразу иметь TLS-сертификат, но его ещё нет.
Поэтому сначала поднимаем всё кроме nginx, выпускаем сертификат на свободном порту 80,
потом поднимаем nginx.

```bash
# 4.1 Всё, кроме nginx (образы скачаются с GHCR; backend прогонит миграции БД)
$COMPOSE up -d postgres redis minio backend frontend
$COMPOSE ps                       # статусы; ждём healthy
docker compose logs -f backend    # смотрим миграции; выход — Ctrl+C

# 4.2 Выпуск сертификата Let's Encrypt (порт 80 свободен → режим standalone)
docker run --rm -p 80:80 \
  -v smart-parking_letsencrypt:/etc/letsencrypt \
  -v smart-parking_acme_webroot:/var/www/certbot \
  certbot/certbot certonly --standalone \
  -d <domain> --email you@company.kz --agree-tos --no-eff-email

# 4.3 Поднять nginx и остальное
$COMPOSE up -d
$COMPOSE ps
```
> Имя тома — `<папка>_letsencrypt`; для `/opt/smart-parking` это
> `smart-parking_letsencrypt`. Проверить: `docker volume ls`.

**Автопродление.** Сертификат живёт 90 дней; сервис `certbot` продлевает его каждые
12 ч, но nginx подхватит новый только после перезагрузки конфига. Добавь ночной cron
под `deploy` (`crontab -e`):
```
0 3 * * * cd /opt/smart-parking && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T nginx nginx -s reload
```

**Проверка:** открой `https://<domain>/health` (или `curl -I https://<domain>/health`)
— должно быть `200`. Сайт открывается с замочком, `/docs` доступен.

На этом ручной деплой работает. Дальше — автоматизация из GitHub.

---

## Шаг 5. Автодеплой из GitHub

На сайте GitHub, репозиторий **tilegen6/parking → Settings**.

- **Secrets and variables → Actions → Variables**: `PROD_DOMAIN` = `<domain>`
  *(только имя хоста, без https:// и пути; вшивается в бандл фронта).*
  Без значения frontend обращается к API на том же origin; образы можно собирать до настройки VPS.
- **Secrets and variables → Actions → Secrets**:
  - `DEPLOY_HOST` = `<IP>`
  - `DEPLOY_USER` = `deploy`
  - `DEPLOY_SSH_KEY` = содержимое **приватного** `deploy_ci` целиком
    (`Get-Content $HOME\deploy_ci`, вместе со строками `-----BEGIN…`/`-----END…`)
  - `DEPLOY_SSH_PORT` = `22` (если не менял)
- **Settings → Environments → New environment → `production`** → включить
  **Required reviewers** и добавить себя. Это ручное подтверждение: job `deploy`
  будет ждать твоего «Approve», если этот механизм доступен для приватного репозитория на вашем тарифе.
  Само указание `environment: production` в workflow не создаёт правило одобрения.
- Только после проверки SSH, домена, `.env` и ручного запуска добавить repository variable
  **`DEPLOY_ENABLED=true`**. Пока переменная отсутствует или имеет другое значение,
  CI проверяет код и публикует образы, а job `deploy` пропускается.
  Перед SSH workflow проверяет наличие обязательных значений, не выводя их содержимое.

Образы проекта: `ghcr.io/tilegen6/smart-parking-backend` и
`ghcr.io/tilegen6/smart-parking-frontend`; эти же имена использует production Compose.
Адрес VPS, домен и SSH-ключ должны быть реальными; их отсутствие не заменяется фиктивными настройками.

После настройки цикл такой: push в `main` → CI собирает и пушит образы
(`sha-<sha>`, `latest`) → при `DEPLOY_ENABLED=true` запускается job `deploy`.
Если настроены Required reviewers, сначала нажмите **Review deployments → Approve**;
затем CI заходит на сервер и обновляет контейнеры.

---

## Шаг 6. Смоук-тест
- `curl -I https://<domain>/health` → `200`; TLS валиден (проверь на ssllabs.com).
- Фронт открывается, `/docs` доступен, `/photos/...` отдаёт из MinIO.
- Создать тариф, прогнать въезд/выезд в «Студии».
- Снаружи только 80/443: `sudo ufw status`, `sudo ss -tlnp | grep -E ':80|:443'`.

---

## Шаг 7. Подключение Kaspi (когда инфраструктура стабильна)
1. Передать Kaspi callback-URL `https://<domain>/api/kaspi/pay` и regex номера авто;
   получить их IP-подсети и (при наличии) Basic-Auth.
2. В `.env`: `KASPI_ALLOWED_IPS=<подсети Kaspi>`, при необходимости
   `KASPI_PROVIDER_USERNAME/PASSWORD`; затем `KASPI_PROVIDER_ENABLED=true`
   (позже `PAYMENT_PROVIDER=kaspi`, `KASPI_AUTOPAY_ENABLED=true` + autopay-creds).
3. `$COMPOSE up -d backend`. Убедиться, что исходящий 443 на `autopayments.kaspi.kz`
   открыт. Прогнать check/pay с тестового терминала Kaspi.
   (Edge-nginx уже проставляет `X-Forwarded-For` — backend видит реальный IP Kaspi.)

---

## Откат на предыдущую версию
На сервере запусти образы по старому тегу коммита:
```bash
IMAGE_TAG=sha-<старый-sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d
```
(миграции БД — только вперёд; при откате схемы учитывай это.)

## Полезные команды
```bash
$COMPOSE ps                       # статусы контейнеров
$COMPOSE logs -f backend          # логи backend (Ctrl+C выйти)
$COMPOSE restart backend          # перезапустить один сервис
$COMPOSE down                     # остановить весь стек (данные в томах не трогает)
docker volume ls                  # список томов (данные БД/MinIO/сертификаты)
```
