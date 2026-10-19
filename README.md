# Smart Parking ANPR

Дипломный проект: система управления въездом, парковочными сессиями и выездом по автомобильному номеру. Оператор получает журнал событий и сессий; администратор управляет камерами, тарифами и правами; водитель оплачивает стоянку через интеграцию с провайдером.

Проблема — разрыв между распознаванием номера, правилами доступа и расчётом оплаты: повторные события, ошибки OCR и потерянный выезд могут приводить к неверным сессиям и суммам. Цель проекта — связать эти операции в проверяемый процесс с журналом решений и безопасной обработкой исключений.

## Команда и границы

| Участник | GitHub | Зона ответственности |
|---|---|---|
| Tilegen Tolegenuly / Тілеген Төлегенұлы (Толик) | [tilegen6](https://github.com/tilegen6) | CV: оценка распознавания, нормализация KZ-номеров, контракт событий; интеграция с API и экраном распознавания |
| Meirambekov Nursultan (Нурсултан) | [kimbiled](https://github.com/kimbiled) | Интерфейс оператора, API сессий, тарифы, роли и тесты бизнес-логики |
| Ақылбек Сабыржан / Sabyrzhan Akylbek (Акыл) | [sabyrzzhan](https://github.com/sabyrzzhan) | Docker, CI, конфигурация, наблюдаемость, резервное копирование и воспроизводимость |

Руководитель: **Айгерим Кыдырбекова / Aigerim Kydyrbekova**; по сообщению команды GitHub-аккаунта нет. Согласование материалов и отзыв **не получены в рамках этой подготовки**. Заказчик со слов команды — владелец сети ресторанов Arka Company; имеется устная договорённость о разработке на базе компании с интеграцией Kaspi. Подробности и границы подтверждения: [актуальность](docs/pre-defense/02-relevance.md), [отзывы и доступ](docs/pre-defense/11-feedback-access.md).

MVP охватывает один объект с въездом и выездом, распознавание, сессии, списки доступа, тарифы, демонстрационный платёж и рабочее место оператора. Собственное обучение OCR — исследовательский следующий этап, а не подтверждённый результат текущей версии. Коммерческий запуск, сертификация безопасности шлагбаума и подтверждённая точность на объекте в MVP не заявляются.

## Состояние и материалы

Статус на 20 октября 2026: код прототипа существует; пакет анализа и проектирования подготовлен к рассмотрению. Реальные интервью, отзыв руководителя и независимое командное ревью требуют подтверждений. [Полный комплект и соответствие требованиям](docs/pre-defense/00-index.md), [проверки](docs/pre-defense/12-verification-results.md), [ограничения и происхождение истории](docs/pre-defense/13-submission.md).

YouTrack исключён из этой работы по указанию владельца. [Распределение задач, сроки и риски](docs/pre-defense/10-management.md) ведутся в Markdown; это не подтверждение выполнения требования комиссии о YouTrack.

Стек по исходнику: Python/FastAPI, SQLAlchemy/Alembic, PostgreSQL 16, MinIO, Redis 7; React 18/TypeScript/Vite; отдельный CV-сервис с заменяемыми детектором и OCR. Docker Compose и Nginx; конфигурации Prometheus, Grafana, Loki и резервного копирования. Redis присутствует в инфраструктуре, но надёжная очередь распознавания не заявляется реализованной.

```text
backend/                 API, модели, миграции, tests/
cv/                      сервис, recognizer/, контракт, tests/, samples/
frontend/                React, страницы и клиент API
deploy/                  Nginx, мониторинг и алерты
docs/pre-defense/        предложение, исследование, требования, решения
  diagrams/              редактируемые источники и SVG
  prototype/             автономный кликабельный макет
scripts/check_submission.py  проверка комплекта и ссылок
.github/workflows/       проверки проекта и документов
```

## Запуск

Нужны Git, Docker Engine с Compose v2; для отдельных проверок — Python 3.12 и Node.js 20+. Репозиторий приватный: сначала получите доступ со своего GitHub. Команды ниже выполняются из корня репозитория; `backend/README.md` и старые CV-заметки отражают более ранние этапы, при расхождении используйте этот раздел.

```powershell
git clone https://github.com/tilegen6/parking.git
cd parking
Copy-Item .env.example .env
```

В локальном `.env` задайте собственные `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, `JWT_SECRET_KEY`, `DEFAULT_ADMIN_PASSWORD`; добавьте `DEFAULT_ADMIN_USERNAME=admin`. Пароль Grafana нужно задать даже для базового запуска: Compose интерполирует обязательные переменные до применения профилей. Для учебного стенда оставьте `PAYMENT_PROVIDER=mock`, `KASPI_PROVIDER_ENABLED=false`, `KASPI_AUTOPAY_ENABLED=false`. Файл `.env` игнорируется Git. Реальные реквизиты, номера клиентов и фотографии в репозиторий не добавляйте. Производственное размещение требует отдельной проверки сети, доступа и настроек.

```powershell
docker compose up -d --build
docker compose ps
```

Интерфейс: http://localhost:5173; API: http://localhost:8000/docs; состояние: http://localhost:8000/health. Миграции выполняются при запуске backend. Войдите заданными локальными данными начального администратора. Для просмотра макета приложение и камера не нужны: откройте [prototype/index.html](docs/pre-defense/prototype/index.html) локально либо выполните `python -m http.server 8086 --bind 127.0.0.1` и перейдите на http://127.0.0.1:8086/docs/pre-defense/prototype/.

CV-профиль по умолчанию использует внешние веса при первом распознавании. Он **не нужен** для документов и тестов ниже; в этой подготовке веса не загружаются. Мониторинг включается отдельно: `docker compose --profile monitoring up -d` после задания `GRAFANA_ADMIN_PASSWORD`. Резервные копии: профиль `backup`; успешный запуск контейнера не заменяет проверку восстановления.

## Проверки

Окружения backend и CV создаются отдельно из-за различающихся версий зависимостей. Из корня:

```powershell
python scripts/check_submission.py all
python -m venv .venv-backend
.venv-backend/Scripts/python -m pip install -r backend/requirements.txt
.venv-backend/Scripts/python -m ruff check backend
.venv-backend/Scripts/python -m ruff format --check backend
Push-Location backend
../.venv-backend/Scripts/python -m pytest -q
Pop-Location

python -m venv .venv-cv
.venv-cv/Scripts/python -m pip install -r cv/requirements.txt -r cv/requirements-dev.txt
.venv-cv/Scripts/python -m ruff check cv
.venv-cv/Scripts/python -m ruff format --check cv
Push-Location cv
../.venv-cv/Scripts/python -m pytest -q
Pop-Location

Push-Location frontend
npm ci
npm run lint
npm run typecheck
npm run build
Pop-Location
```

На Linux вместо `Scripts/python` используйте `bin/python`, вместо PowerShell-переходов — `cd`. API-тесты используют изолированную SQLite и подмены интеграций; они не подтверждают работу PostgreSQL, реальных платежей и оборудования. Типизация в исходном CI носит рекомендательный характер. [План полевых испытаний и метрики](docs/pre-defense/09-evaluation.md).

## Внесение изменений и сдача

Работайте со своего аккаунта в отдельной ветке; указывайте результат и проверки в Pull Request. Перед включением в `main` требуется настоящее ревью другого участника. Запрещены искусственные отзывы и выдача импортированных дат за фактическое время работы. Теги сдачи неизменяемы; правила и сценарий демонстрации — в [карточке сдачи](docs/pre-defense/13-submission.md).
