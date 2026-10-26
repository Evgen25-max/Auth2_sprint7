
from typing import Optional

from core.config import config

from redis.asyncio import Redis

redis: Optional[Redis] = None


def init_redis() -> None:
    """Инициализирует клиент."""
    global redis
    redis = Redis(
        host=config.REDIS_AUTH_HOST,
        port=config.REDIS_AUTH_PORT,
        db=config.REDIS_AUTH_DB,
        password=config.REDIS_AUTH_PASSW,
        socket_connect_timeout=config.REDIS_CONNECT_TIMEOUT,
        socket_timeout=config.REDIS_SOCKET_TIMEOUT,
        decode_responses=True,
    )

async def close_redis() -> None:
    """Закрывает клиент."""
    global redis
    if redis is not None:
        await redis.aclose()
        redis = None


def get_redis() -> Redis:
    """Возвращает клиент."""
    if redis is None:
        raise RuntimeError(
            'Redis не инициализирован. Вызовите init_redis() при старте.'
        )
    return redis
