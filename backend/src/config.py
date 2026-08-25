"""Конфигурация приложения. Все значения берутся из переменных окружения (.env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env лежит в корне репозитория (рядом с docker-compose).
        # "../.env" — когда backend запущен локально из папки backend/;
        # ".env" — запасной вариант. В Docker переменные приходят из окружения.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Smart Parking ANPR"
    app_env: str = "local"
    debug: bool = True
    log_level: str = "INFO"

    # --- PostgreSQL ---
    postgres_user: str = "parking_user"
    # Секрет: без значения по умолчанию — обязателен, иначе приложение упадёт
    # с понятной ошибкой (никаких «паролей» в коде).
    postgres_password: str
    postgres_db: str = "parking_db"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    # Пароль опционален: пусто = без авторизации (для простого локального запуска)
    redis_password: str = ""

    # --- MinIO ---
    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minio_admin"
    # Секрет: без значения по умолчанию — обязателен
    minio_root_password: str
    minio_bucket: str = "parking-photos"
    minio_secure: bool = False
    # Публичный адрес, по которому фронтенд скачивает фото (если отличается от endpoint)
    minio_public_url: str = "http://localhost:9000"

    # --- Parking sessions (ТЗ §2.4, §6.2) ---
    # Порог уверенности: ниже — событие low_confidence, сессия не создаётся
    recognition_min_confidence: float = 0.85
    # Окно дедупликации повторных событий одного номера, секунд
    session_dedup_window_seconds: int = 30
    # Серия дублей ENTRY (машина стоит перед шлагбаумом): пока события идут не
    # реже этого окна, старт сессии сдвигается на последнее из них. Вне окна —
    # повторное распознавание давно стоящей машины, счёт не обнуляем.
    entry_restart_window_seconds: int = 600
    # ТС-3: новый ENTRY при активной сессии позже этого срока = пропущенный
    # выезд. Старую сессию закрываем как auto_closed, открываем новую.
    reentry_new_session_seconds: int = 3600
    # ТС-8: активная сессия старше этого срока помечается «зависшей» (stale)
    session_stale_after_hours: int = 24

    # --- Auth / JWT ---
    # Секрет подписи JWT. В проде — задать через env; дефолт только для dev/CI.
    jwt_secret_key: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720  # 12 часов
    # Стартовый администратор — создаётся при пустой таблице пользователей.
    default_admin_username: str = "admin"
    default_admin_password: str = "admin"

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Payments: активный провайдер оплаты ---
    # mock  — заглушка (оплата подтверждается webhook'ом из Студии, дефолт для dev/CI)
    # kaspi — реальный провайдер Kaspi.kz (онлайн-протокол, см. modules/kaspi.py)
    payment_provider: str = "mock"

    # --- Kaspi: онлайн-протокол провайдера (входящий, Kaspi -> нас) ---
    # Kaspi дёргает наш GET /api/kaspi/pay (command=check|pay). Монтируется только
    # при включённом флаге; защита — IP-allowlist (+ опц. Basic Auth).
    kaspi_provider_enabled: bool = False
    # Подсети Kaspi, с которых приходят запросы (Протокол взаимодействия, п.1)
    kaspi_allowed_ips: str = (
        "194.187.247.152,194.187.245.108,197.187.244.108,194.187.244.108"
    )
    # Опциональная Basic Auth поверх IP-allowlist (пусто = не проверяем)
    kaspi_provider_username: str = ""
    kaspi_provider_password: str = ""
    # Формат ответа Kaspi: xml (основной по спецификации) | json
    kaspi_provider_response_format: str = "xml"
    # Шаблон QR/deeplink для pay_url провайдера ({account} = номер авто). Пусто —
    # pay_url не формируется (оплата инициируется в приложении Kaspi).
    kaspi_pay_deeplink_template: str = ""

    # --- Kaspi: AutomaticPayments (исходящий, мы -> autopayments.kaspi.kz) ---
    # Автосписание с привязанной карты при въезде/выезде. Basic Auth.
    kaspi_autopay_enabled: bool = False
    kaspi_autopay_base_url: str = "https://autopayments.kaspi.kz"
    kaspi_autopay_username: str = ""
    kaspi_autopay_password: str = ""
    # ID парковки в системе Kaspi + бесплатное время (сек), передаётся в enter
    kaspi_parking_id: int = 1
    kaspi_free_time_seconds: int = 0
    # Таймаут запроса к Kaspi (ТЗ: ответ провайдера ≤ 15 c)
    kaspi_http_timeout_seconds: float = 15.0

    # --- CV-сервис (распознавание живого потока) ---
    # Внутри docker-сети — по имени сервиса; локально — http://localhost:8090
    cv_service_url: str = "http://cv:8090"

    @property
    def database_url(self) -> str:
        """Async-строка подключения для SQLAlchemy / asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync-строка подключения для Alembic-миграций."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        # Если задан пароль — включаем его в строку подключения (redis://:pass@host)
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def kaspi_allowed_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.kaspi_allowed_ips.split(",") if ip.strip()]


@lru_cache
def get_settings() -> Settings:
    # Обязательные поля (пароли) приходят из окружения/.env, а не из аргументов —
    # mypy об этом не знает, поэтому глушим его call-arg для этого вызова.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
