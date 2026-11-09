import logging
from concurrent.futures import ThreadPoolExecutor, Future

import redis
from django.conf import settings
from opentelemetry import trace
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="view-stats")

_STATS_KEY = "stats:views"
_PENDING_KEY = "stats:pending"


def _client() -> redis.Redis:
    return redis.Redis(
        host=settings.STATS_REDIS_HOST,
        port=settings.STATS_REDIS_PORT,
        password=settings.STATS_REDIS_PASSW,
        db=0,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _do_increment(film_id: str, request_id: str | None) -> None:
    """Тело инкремента, выполняется в потоке пула. Ошибки НЕ всплывают в request."""
    with tracer.start_as_current_span("ViewStats.increment") as span:
        span.set_attribute("stats.film_id", film_id)
        if request_id:
            # X-Request-Id (генерится, если заголовок не пришёл)
            span.set_attribute("http.request_id", request_id)
        try:
            r = _client()
            r.hincrby(_STATS_KEY, film_id, 1)
        except redis.RedisError as e:
            logger.warning("view-stats increment failed for %s: %s", film_id, e)
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)


def increment_view(film_id: str, request_id: str | None = None) -> Future:
    """
    Fire-and-forget инкремент. Возвращает Future (можно await в тестах).
    """
    return _executor.submit(_do_increment, str(film_id), request_id)
