"""Конфигурация приложения. Все значения берутся из переменных окружения / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Игнорируем переменные, которые ещё не описаны в этом классе
        # (POSTGRES_*, MINIO_*, CAMERA_* и т.д.) — добавим их по мере надобности.
        extra="ignore",
    )

    # --- Приложение ---
    APP_NAME: str = "smart-parking"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Origin'ы фронтенда одной строкой через запятую (как в .env)
    CORS_ORIGINS: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """Разбивает CORS_ORIGINS в список, отбрасывая пустые элементы."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Кэшируем настройки, чтобы .env читался один раз за процесс."""
    return Settings()


settings = get_settings()
