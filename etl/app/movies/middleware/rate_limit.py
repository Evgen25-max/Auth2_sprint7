
import logging
import time
import uuid
from functools import lru_cache
from typing import Mapping

import redis
from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _ratelimit_client() -> redis.Redis:
    return redis.Redis(
        host=getattr(settings, 'REDIS_HOST', 'redis'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        password=getattr(settings, 'REDIS_PASSW', None),
        db=getattr(settings, 'REDIS_CACHE_DB', 0),
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )

def trusted_client_ip(headers: Mapping[str, str], remote_addr: str | None) -> str:
    """
    Доверенный IP клиента. Порядок источников:
      1. X-Real-IP  — ставит nginx как $remote_addr, перезаписывается, не подделывается.
      2. X-Forwarded-For[-1] — последний элемент цепочки = $remote_addr, дописанный nginx.
         (первый элемент мог быть подделан клиентом при $proxy_add_x_forwarded_for)
      3. remote_addr — прямой доступ мимо nginx (uvicorn на 8001/8002 с хоста).
    """
    real_ip = headers.get('X-Real-IP') or headers.get('HTTP_X_REAL_IP')
    if real_ip:
        return real_ip.strip()

    xff = headers.get('X-Forwarded-For') or headers.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[-1].strip()

    return remote_addr or 'unknown'


class RateLimitMiddleware:

    EXEMPT_PREFIXES = ('/static/', '/media/', '/favicon.ico', '/health')

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_requests = getattr(settings, 'RATE_LIMIT_REQUESTS', 100)
        self.window = getattr(settings, 'RATE_LIMIT_PERIOD', 60)

    def __call__(self, request):
        if any(request.path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return self.get_response(request)

        client = _ratelimit_client()
        if client is None:
            return self.get_response(request)

        ip = self._client_ip(request)
        key = f'ratelimit:{ip}'

        try:
            allowed, remaining, reset_at = self._check(key, client)
        except redis.RedisError as e:
            # Redis лёг — пропускаем
            logger.warning('Redis недоступен, пропускаю rate limiting: %s', e)
            return self.get_response(request)

        if not allowed:
            retry_after = max(1, int(reset_at - time.time()) + 1)
            return JsonResponse(
                {'detail': 'Too Many Requests'},
                status=429,
                headers={
                    'Retry-After': str(retry_after),
                    'X-RateLimit-Limit': str(self.max_requests),
                    'X-RateLimit-Remaining': '0',
                },
            )

        response = self.get_response(request)
        response['X-RateLimit-Limit'] = str(self.max_requests)
        response['X-RateLimit-Remaining'] = str(remaining)
        return response

    def _check(self, key: str, client: redis.Redis) -> tuple[bool, int, float]:
        now = time.time()
        window_start = now - self.window
        # уникальный member, чтобы не терять запросы при коллизии str(now)
        member = f'{now}:{uuid.uuid4().hex[:8]}'

        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, self.window + 1)
        pipe.zrange(key, 0, 0, withscores=True)
        results = pipe.execute()

        current_count = int(results[2])
        oldest = results[4]
        reset_at = (oldest[0][1] + self.window) if oldest else (now + self.window)

        allowed = current_count <= self.max_requests
        remaining = max(0, self.max_requests - current_count)
        return allowed, remaining, reset_at


    @staticmethod
    def _client_ip(request) -> str:
        return trusted_client_ip(request.META, request.META.get('REMOTE_ADDR'))