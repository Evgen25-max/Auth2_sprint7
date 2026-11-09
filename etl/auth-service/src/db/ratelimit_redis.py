
from typing import Optional

from redis.asyncio import Redis

from core.config import config

ratelimit_redis: Optional[Redis] = None


def init_ratelimit_redis() -> None:
    """Инициализирует клиент cache-redis для rate-limit."""
    global ratelimit_redis
    ratelimit_redis = Redis(
        host=config.RATELIMIT_REDIS_HOST,
        port=config.RATELIMIT_REDIS_PORT,
        db=config.RATELIMIT_REDIS_DB,
        password=config.RATELIMIT_REDIS_PASSW,
        socket_connect_timeout=config.REDIS_CONNECT_TIMEOUT,
        socket_timeout=config.REDIS_SOCKET_TIMEOUT,
        decode_responses=True,
    )


async def close_ratelimit_redis() -> None:
    """Закрывает клиент cache-redis для rate-limit."""
    global ratelimit_redis
    if ratelimit_redis is not None:
        await ratelimit_redis.aclose()
        ratelimit_redis = None


def get_ratelimit_redis() -> Redis:
    """Возвращает клиент cache-redis для rate-limit."""
    if ratelimit_redis is None:
        raise RuntimeError(
            'Rate-limit Redis не инициализирован. '
            'Вызовите init_ratelimit_redis() при старте.'
        )
    return ratelimit_redis