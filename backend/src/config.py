"""Конфигурация приложения. Все значения берутся из переменных окружения (.env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Application ---
    app_name: str = "Smart Parking ANPR"
    app_env: str = "local"
    debug: bool = True
    log_level: str = "INFO"

    # --- PostgreSQL ---
    postgres_user: str = "parking_user"
    postgres_password: str = "parking_password"
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
    minio_root_password: str = "minio_password"
    minio_bucket: str = "parking-photos"
    minio_secure: bool = False
    # Публичный адрес, по которому фронтенд скачивает фото (если отличается от endpoint)
    minio_public_url: str = "http://localhost:9000"

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def database_url(self) -> str:
        """Async-строка подключения для SQLAlchemy / asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
