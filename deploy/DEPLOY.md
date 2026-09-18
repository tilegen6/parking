# Production deploy — Ubuntu 24 VPS (ps.kz)

Первый прод-деплой и дальнейшая доставка через CI/CD. Стек: `docker-compose.yml`
(база) + `docker-compose.prod.yml` (оверлей: образы из GHCR, edge-nginx + TLS,
внутренние порты закрыты). Наружу открыты только **80/443**.

Плейсхолдеры: `<domain>` — прод-домен, `codeanpr` — владелец GHCR (в нижнем регистре),
приложение живёт в `/opt/smart-parking`.

---

## 0. Предпосылки
- Домен `<domain>` с A-записью на публичный IP VPS (Let's Encrypt не выдаёт сертификат
  на голый IP). Проверить: `dig +short <domain>` → IP VPS.
- Доступ по SSH под root/sudo для первичной настройки.

## 1. Подготовка сервера (один раз)
```bash
# 1.1 Пользователь для деплоя
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
install -d -m700 -o deploy -g deploy /home/deploy/.ssh
# положить ваш админ-ключ + ПУБЛИЧНЫЙ ключ CI в authorized_keys:
#   /home/deploy/.ssh/authorized_keys  (chmod 600, owner deploy)

# 1.2 Docker Engine + compose plugin (официальный репозиторий)
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy

# 1.3 Фаервол: только SSH + HTTP + HTTPS
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 1.4 SSH hardening (/etc/ssh/sshd_config): PermitRootLogin no, PasswordAuthentication no
systemctl restart ssh
```
Ключ для CI: сгенерируйте отдельную пару (`ssh-keygen -t ed25519 -f deploy_ci -N ""`),
публичную часть → `authorized_keys` пользователя `deploy`, приватную → секрет
`DEPLOY_SSH_KEY` (см. §5).

## 2. Приложение и секреты
```bash
sudo -iu deploy
git clone https://github.com/CodeANPR/smart-parking.git /opt/smart-parking
cd /opt/smart-parking
git checkout main
cp .env.example .env
```
Заполнить `/opt/smart-parking/.env` (chmod 640) прод-значениями:
```
APP_ENV=production
DEBUG=false
DOMAIN=<domain>
SERVICE_URL=https://<domain>
CORS_ORIGINS=https://<domain>
MINIO_PUBLIC_URL=https://<domain>/photos
# сгенерировать: openssl rand -hex 32
SECRET_KEY=…
JWT_SECRET_KEY=…
POSTGRES_PASSWORD=…
MINIO_ROOT_PASSWORD=…
GRAFANA_ADMIN_PASSWORD=…
# Kaspi пока выключен — включаем на этапе go-live (§7)
PAYMENT_PROVIDER=mock
KASPI_PROVIDER_ENABLED=false
KASPI_AUTOPAY_ENABLED=false
# IMAGE_TAG проставляет CI при деплое; для ручного запуска можно latest
IMAGE_TAG=latest
```

## 3. Доступ к образам GHCR
Пакеты приватные → войти один раз (токен с правом `read:packages`):
```bash
echo <GHCR_TOKEN> | docker login ghcr.io -u <github-user> --password-stdin
```
(Альтернатива: сделать пакеты `-backend`/`-frontend` публичными в GitHub.)

## 4. Первый запуск + TLS
```bash
cd /opt/smart-parking
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup"

# 4.1 Поднять всё, кроме edge-nginx (порт 80 нужен свободным для выпуска сертификата)
$COMPOSE up -d postgres redis minio backend frontend

# 4.2 Первичный выпуск сертификата (standalone, порт 80 свободен)
docker run --rm -p 80:80 \
  -v smart-parking_letsencrypt:/etc/letsencrypt \
  -v smart-parking_acme_webroot:/var/www/certbot \
  certbot/certbot certonly --standalone \
  -d <domain> --email you@example.com --agree-tos --no-eff-email

# 4.3 Поднять edge-nginx + certbot (дальше продление идёт по webroot)
$COMPOSE up -d
$COMPOSE ps          # все healthy; наружу только nginx 80/443
docker compose logs -f backend   # alembic применяет миграции (в т.ч. 0006)
```
> Имя тома — `<projectdir>_letsencrypt`; для `/opt/smart-parking` это
> `smart-parking_letsencrypt` (проверить: `docker volume ls`).

Продление: сервис `certbot` вызывает `certbot renew` каждые 12 ч. nginx подхватывает
новый сертификат при перезагрузке — добавьте cron пользователю `deploy`:
```bash
0 3 * * * cd /opt/smart-parking && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T nginx nginx -s reload
```

## 5. CI/CD (GitHub → Settings)
- **Variables**: `PROD_DOMAIN=<domain>` (вшивается в бандл фронта как `VITE_API_URL`).
- **Secrets**: `DEPLOY_HOST` (IP/домен), `DEPLOY_USER=deploy`,
  `DEPLOY_SSH_KEY` (приватный ключ CI), `DEPLOY_SSH_PORT` (если не 22).
- **Environments → `production`**: включить **Required reviewers** (это и есть ручное
  подтверждение деплоя). Job `deploy` в `ci-cd.yml` ждёт этого approve.

После настройки: push в `main` → CI собирает и пушит образы (`sha-<sha>`, `latest`) →
job `deploy` ждёт approve → по SSH `git pull` + `docker compose pull && up -d` с
`IMAGE_TAG=sha-<sha>`.

## 6. Смоук-тест
- `curl -I https://<domain>/health` → 200; TLS валиден (SSL Labs).
- Фронт открывается, `/docs` доступен, `/photos/...` отдаёт из MinIO.
- Создать тариф, прогнать въезд/выезд в «Студии».
- `ufw status` и `ss -tlnp` — снаружи только 80/443.

## 7. Kaspi go-live (после стабилизации инфраструктуры)
1. Передать Kaspi callback-URL `https://<domain>/api/kaspi/pay` и regex номера авто;
   получить их IP-подсети и (при наличии) Basic-Auth.
2. В `.env`: `KASPI_ALLOWED_IPS=<подсети Kaspi>`, при необходимости
   `KASPI_PROVIDER_USERNAME/PASSWORD`; затем `KASPI_PROVIDER_ENABLED=true`
   (позже `PAYMENT_PROVIDER=kaspi`, `KASPI_AUTOPAY_ENABLED=true` + autopay-creds).
3. `docker compose … up -d backend`. Проверить, что egress 443 на
   `autopayments.kaspi.kz` открыт. Прогнать check/pay с тестового терминала Kaspi.
   (Edge-nginx уже проставляет `X-Forwarded-For` — backend видит реальный IP Kaspi.)

## Откат
Задеплоить предыдущий тег: на сервере
`IMAGE_TAG=sha-<старый-sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d`
(миграции только вперёд — учитывайте при откате схемы).
