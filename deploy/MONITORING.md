# Ops-стек: логи, метрики, алерты, бэкапы

Всё разведено по docker-compose **profiles**, поэтому обычная разработка
остаётся лёгкой.

## Запуск

```bash
# только приложение (backend, frontend, postgres, redis, minio)
docker compose up -d

# + логи, метрики, алерты
docker compose --profile monitoring up -d

# + бэкапы и очистка старых файлов
docker compose --profile backup up -d

# всё сразу
docker compose --profile monitoring --profile backup up -d
```

Перед запуском заполните в `.env` (см. `.env.example`):
`GRAFANA_ADMIN_PASSWORD`, `ALERT_TELEGRAM_BOT_TOKEN`, `ALERT_TELEGRAM_CHAT_ID`.

## Что входит

| Задача | Сервисы | Доступ |
|--------|---------|--------|
| **Логи** backend/frontend и всех контейнеров | Loki + Promtail + Grafana | Grafana → Explore → Loki |
| **Метрики** контейнеров | cAdvisor | Prometheus job `cadvisor` |
| **Метрики** PostgreSQL | postgres-exporter | job `postgres` |
| **Метрики** MinIO | нативные `/minio/v2/metrics` | job `minio` |
| **Метрики** Redis / хоста | redis-exporter / node-exporter | jobs `redis`, `node-exporter` |
| **Доступность сервисов** | blackbox-exporter | job `blackbox-http` |
| **Алерты** при падении | Prometheus + Alertmanager → Telegram | — |
| **Бэкапы** PostgreSQL + ретеншен | postgres-backup | volume `postgres_backups` |
| **Очистка** старых снимков MinIO | minio-lifecycle (ILM) | — |
| **Очистка** старых логов | docker log-rotation + Loki retention (7д) | — |

## UI

- Grafana: http://SERVER:3000 (логин `admin` / `GRAFANA_ADMIN_PASSWORD`).
  Источники Prometheus и Loki подключаются автоматически.
- Prometheus: http://SERVER:9090 (вкладка **Alerts** — статус правил).
- Alertmanager: http://SERVER:9093.

Дашборды можно импортировать по ID: cAdvisor **14282**, PostgreSQL **9628**,
MinIO **13502**, Node Exporter **1860**.

## Алерты

Правила в `deploy/prometheus/alerts.yml`: падение цели (`up==0`), провал
HTTP-пробы, падение контейнера, недоступность PostgreSQL/Redis, перегрузка
CPU/памяти. Канал доставки — Telegram (`deploy/alertmanager/alertmanager.yml.tmpl`,
токен подставляется из `.env` init-контейнером). Для e-mail/Slack — раскомментируйте
соответствующий блок в шаблоне.

## Бэкапы и очистка

- **PostgreSQL**: `postgres-backup` делает дамп по `BACKUP_SCHEDULE` (по
  умолчанию ежедневно) в volume `postgres_backups`; хранит
  `BACKUP_KEEP_DAYS/WEEKS/MONTHS` копий, старые удаляет сам.
  Восстановление: `gunzip -c backup.sql.gz | psql ...`.
- **MinIO**: `minio-lifecycle` ставит правило ILM — снимки старше
  `MINIO_OBJECT_RETENTION_DAYS` (30) удаляются автоматически.
- **Логи**: docker json-file ротируется (10 МБ × 5), в Loki retention 7 дней.
