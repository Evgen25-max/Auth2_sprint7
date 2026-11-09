
import os
from logging import config as logging_config

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.logger import LOGGING

logging_config.dictConfig(LOGGING)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    PROJECT_NAME_FASTAPI: str = 'movies'

    ELASTIC_SCHEMA: str = 'http://'
    ELASTIC_HOST: str = '127.0.0.1'
    ELASTIC_PORT: int = 9200

    # cache-redis: кэш фильмов
    REDIS_HOST: str = '127.0.0.1'
    REDIS_PORT: int = 6379
    REDIS_PASSW: str | None = None
    REDIS_CACHE_DB: int = 0

    # auth-redis: blacklist / perms / user_ver
    REDIS_AUTH_HOST: str = '127.0.0.1'
    REDIS_AUTH_PORT: int = 6380
    REDIS_AUTH_PASSW: str | None = None
    REDIS_AUTH_DB: int = 1

    # Общий rate-limit Redis для всех сервисов.
    RATELIMIT_REDIS_HOST: str = '127.0.0.1'
    RATELIMIT_REDIS_PORT: int = 6379
    RATELIMIT_REDIS_PASSW: str | None = None
    RATELIMIT_REDIS_DB: int = 2

    ES_MAX_RETRIES: int = 3
    ES_REQUEST_TIMEOUT: int = 30

    REDIS_CONNECT_TIMEOUT: int = 5
    REDIS_SOCKET_TIMEOUT: int = 5

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = 'HS256'
    AUTH_SERVICE_URL: str = 'http://127.0.0.1:8001'
    PERMS_CACHE_TTL_SECONDS: int = 900

    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60

    OTEL_EXPORTER_OTLP_ENDPOINT: str

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_ignore_empty=True,
        extra='ignore',
    )


config = Settings()