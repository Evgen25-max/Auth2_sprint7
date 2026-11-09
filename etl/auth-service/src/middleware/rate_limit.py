
"""
Rate limiting middleware для auth-service.

Важно:
  - Для auth-service используем fail-closed.
  - Счётчики живут в cache-redis db=2, а не в auth-redis
"""

import logging
import math
import time
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.http import trusted_client_ip

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Ограничение количества запросов от одного клиента по IP.
    """

    EXEMPT_PREFIXES = (
        '/health',
        '/api/v1/auth/docs',
        '/api/v1/auth/redoc',
        '/api/v1/auth/openapi.json',
    )

    def __init__(
        self,
        app,
        enabled: bool = True,
        max_requests: int = 100,
        window_seconds: int = 60,
    ):
        super().__init__(app)
        self.enabled = enabled
        self.max_requests = max_requests
        self.window = window_seconds

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        if any(request.url.path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return await call_next(request)

        redis_client: Redis | None = getattr(request.app.state, 'ratelimit_redis', None)

        if redis_client is None:
            logger.warning('Rate-limit Redis не инициализирован, fail-closed')
            return JSONResponse(
                status_code=503,
                content={'detail': 'Rate limiter unavailable'},
            )

        client_ip = trusted_client_ip(request) or 'unknown'
        key = f'ratelimit:{client_ip}'

        try:
            allowed, remaining, reset_at = await self._check_rate_limit(key, redis_client)
        except Exception as e:
            # Fail-closed для auth-service.
            logger.warning('Rate-limit Redis недоступен, fail-closed: %s', e)
            return JSONResponse(
                status_code=503,
                content={'detail': 'Rate limiter unavailable'},
            )

        if not allowed:
            retry_after = max(1, math.ceil(reset_at - time.time()))
            return JSONResponse(
                status_code=429,
                content={
                    'detail': 'Too Many Requests',
                    'retry_after': retry_after,
                },
                headers={
                    'Retry-After': str(retry_after),
                    'X-RateLimit-Limit': str(self.max_requests),
                    'X-RateLimit-Remaining': '0',
                },
            )

        response = await call_next(request)
        response.headers['X-RateLimit-Limit'] = str(self.max_requests)
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        return response

    async def _check_rate_limit(
        self,
        key: str,
        redis_client: Redis,
    ) -> tuple[bool, int, float]:
        """
        Sliding window log: храним timestamp каждого запроса в sorted set.
        """
        now = time.time()
        window_start = now - self.window

        member = f'{now}:{uuid.uuid4().hex[:8]}'

        pipe = redis_client.pipeline(transaction=True)

        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, self.window + 1)
        pipe.zrange(key, 0, 0, withscores=True)

        results = await pipe.execute()

        current_count = int(results[2])
        oldest_entries = results[4]

        if oldest_entries:
            oldest_ts = float(oldest_entries[0][1])
            reset_at = oldest_ts + self.window
        else:
            reset_at = now + self.window

        allowed = current_count <= self.max_requests
        remaining = max(0, self.max_requests - current_count)

        return allowed, remaining, reset_at