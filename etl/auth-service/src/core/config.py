
import os
from functools import cached_property
from logging import config as logging_config

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.logger import LOGGING

logging_config.dictConfig(LOGGING)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    """Настройки auth-service, читаемые из .env."""

    PROJECT_NAME: str = 'auth'

    POSTGRES_HOST: str = '127.0.0.1'
    POSTGRES_PORT: int = 5432
    POSTGRES_AUTH_USER: str = 'auth_admin'
    POSTGRES_AUTH_PASSWORD: str = 'secret'
    POSTGRES_AUTH_DB: str = 'auth_service_db'
    POSTGRES_AUTH_SCHEMA: str = 'auth'
    POSTGRES_ECHO: bool = False

    POSTGRES_AUTH_APP_USER: str = 'auth_app'
    POSTGRES_AUTH_APP_PASSWORD: str = 'secret'

    # auth-redis:
    REDIS_AUTH_HOST: str = 'auth-redis'
    REDIS_AUTH_PORT: int = 6380
    REDIS_AUTH_PASSW: str | None = None
    REDIS_AUTH_DB: int = 1
    REDIS_CONNECT_TIMEOUT: int = 5
    REDIS_SOCKET_TIMEOUT: int = 5

    # cache-redis:
    RATELIMIT_REDIS_HOST: str = 'redis'
    RATELIMIT_REDIS_PORT: int = 6379
    RATELIMIT_REDIS_PASSW: str | None = None
    RATELIMIT_REDIS_DB: int = 2

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60

    # Account lockout
    LOGIN_FAILED_THRESHOLD: int = 5
    LOGIN_FAILED_WINDOW_SEC: int = 300
    LOGIN_LOCKOUT_SEC: int = 900

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    PERMS_CACHE_TTL_SECONDS: int = 60 * 15

    PASSWORD_PEPPER: str

    OTEL_EXPORTER_OTLP_ENDPOINT: str

    # Yandex OAuth
    YANDEX_CLIENT_ID: str
    YANDEX_CLIENT_SECRET: str
    YANDEX_REDIRECT_URI: str
    YANDEX_AUTH_URL: str
    YANDEX_TOKEN_URL: str
    YANDEX_INFO_URL: str

    # VK OAuth
    VK_CLIENT_ID: str = ''
    VK_CLIENT_SECRET: str = ''
    VK_REDIRECT_URI: str = 'http://127.0.0.1:8080/auth/callback'

    INTERNAL_API_KEY: str

    @cached_property
    def database_url(self) -> str:
        return (
            f'postgresql+asyncpg://{self.POSTGRES_AUTH_APP_USER}'
            f':{self.POSTGRES_AUTH_APP_PASSWORD}'
            f'@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}'
            f'/{self.POSTGRES_AUTH_DB}'
        )

    @cached_property
    def migration_url(self) -> str:
        return (
            f'postgresql+asyncpg://{self.POSTGRES_AUTH_USER}'
            f':{self.POSTGRES_AUTH_PASSWORD}'
            f'@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}'
            f'/{self.POSTGRES_AUTH_DB}'
        )

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_ignore_empty=True,
        extra='ignore',
    )


config = Settings()