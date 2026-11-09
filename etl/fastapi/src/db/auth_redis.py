
from typing import Optional

from redis.asyncio import Redis

from core.config import config

auth_redis: Optional[Redis] = None


def init_auth_redis() -> None:
    """Инициализирует клиент auth-redis."""
    global auth_redis
    auth_redis = Redis(
        host=config.REDIS_AUTH_HOST,
        port=config.REDIS_AUTH_PORT,
        db=config.REDIS_AUTH_DB,
        password=config.REDIS_AUTH_PASSW,
        socket_connect_timeout=config.REDIS_CONNECT_TIMEOUT,
        socket_timeout=config.REDIS_SOCKET_TIMEOUT,
        decode_responses=True,
    )


async def close_auth_redis() -> None:
    """Закрывает клиент auth-redis."""
    global auth_redis
    if auth_redis is not None:
        await auth_redis.close()
        auth_redis = None


def get_auth_redis() -> Optional[Redis]:
    """
    Возвращает auth-redis или None, если он не инициализирован.
    """
    return auth_redis