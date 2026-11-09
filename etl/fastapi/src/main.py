
"""
Точка входа FastAPI-сервиса выдачи фильмов.
- работает даже при недоступности Redis/ES/Auth-сервиса;
- rate-limit использует общий Redis db=2;
- auth-состояние читается из auth-redis db=1.
"""
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from elasticsearch import ConnectionTimeout
from elasticsearch.exceptions import ConnectionError as ESConnectionError
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api.v1 import films
from cache.redis_film import RedisFilmCache
from core.auth_integration import get_auth_client
from core.config import config
from core.logger import LOGGING
from db import elastic, redis
from db import auth_redis as auth_redis_module
from db import ratelimit_redis as ratelimit_redis_module
from db_work.elastic_film import ElasticFilmRepository
from middleware.rate_limit import RateLimitMiddleware
from middleware.request_id import RequestIDMiddleware
from services.custom_exceptions import (
    FilmNotFoundError,
    FilmDataError,
    IndexNotFoundError,
)
from services.film import FilmService
from tracing import configure_tracer

# --- Логирование ---
logging.config.dictConfig(LOGGING)
logger = logging.getLogger(__name__)


# --- Lifespan: управление жизненным циклом ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения.

    Graceful degradation: приложение стартует даже если Redis/ES/Auth недоступны,
    но с ограниченным функционалом.
    """
    logger.info('Запуск приложения %s...', config.PROJECT_NAME_FASTAPI)

    # 1. Инициализация cache-redis для кэша фильмов.
    try:
        redis.init_redis()
        logger.info('Cache Redis клиент инициализирован')
    except Exception as e:
        logger.error('Не удалось инициализировать Cache Redis клиент: %s', e)

    # 2. Инициализация auth-redis для blacklist / perms / user_ver.
    try:
        auth_redis_module.init_auth_redis()
        logger.info('Auth Redis клиент инициализирован')
    except Exception as e:
        logger.error('Не удалось инициализировать Auth Redis: %s', e)

    # 3. Инициализация общего rate-limit Redis.
    try:
        ratelimit_redis_module.init_ratelimit_redis()
        logger.info('Rate-limit Redis клиент инициализирован')
    except Exception as e:
        logger.error('Не удалось инициализировать Rate-limit Redis: %s', e)

    # 4. Инициализация Elasticsearch.
    try:
        elastic.init_elastic()
        logger.info('Elasticsearch клиент инициализирован')
    except Exception as e:
        logger.error('Не удалось инициализировать Elasticsearch клиент: %s', e)

    # 5. Инициализация AuthClient для интеграции с Auth-сервисом.
    try:
        app.state.auth_client = get_auth_client()
        logger.info('AuthClient инициализирован (URL: %s)', config.AUTH_SERVICE_URL)
    except Exception as e:
        logger.warning('AuthClient не инициализирован: %s', e)
        app.state.auth_client = None

    # 6. Проверка доступности cache-redis.
    try:
        r = redis.get_redis()
        if r is not None:
            await r.ping()
            app.state.redis = r
            logger.info('Cache Redis доступен')
        else:
            app.state.redis = None
    except Exception as e:
        app.state.redis = None
        logger.warning('Cache Redis недоступен при старте: %s. Кэш фильмов будет деградировать.', e)

    # 7. Проверка доступности auth-redis.
    try:
        ar = auth_redis_module.get_auth_redis()
        if ar is not None:
            await ar.ping()
            app.state.auth_redis = ar
            logger.info('Auth Redis доступен')
        else:
            app.state.auth_redis = None
            logger.warning('Auth Redis не инициализирован. Protected-эндпоинты будут fail-closed.')
    except Exception as e:
        app.state.auth_redis = None
        logger.warning(
            'Auth Redis недоступен при старте: %s. Protected-эндпоинты будут fail-closed.',
            e,
        )

    # 8. Проверка доступности общего rate-limit Redis.
    try:
        rr = ratelimit_redis_module.get_ratelimit_redis()
        if rr is not None:
            await rr.ping()
            app.state.ratelimit_redis = rr
            logger.info('Rate-limit Redis доступен')
        else:
            app.state.ratelimit_redis = None
            logger.warning('Rate-limit Redis не инициализирован. Rate limiting будет отключён.')
    except Exception as e:
        app.state.ratelimit_redis = None
        logger.warning('Rate-limit Redis недоступен при старте: %s. Rate limiting будет отключён.', e)

    # 9. Проверка доступности Elasticsearch.
    try:
        await elastic.get_elastic().info()
        logger.info('Elasticsearch доступен')
    except Exception as e:
        logger.warning('Elasticsearch недоступен при старте: %s', e)

    # 10. Инициализация FilmService.
    try:
        r = redis.get_redis()
        es = elastic.get_elastic()
        app.state.film_service = FilmService(
            cache=RedisFilmCache(r),
            repository=ElasticFilmRepository(es),
        )
        logger.info('FilmService инициализирован')
    except Exception as e:
        logger.error('Не удалось инициализировать FilmService: %s', e)
        app.state.film_service = None

    logger.info('Приложение %s запущено', config.PROJECT_NAME_FASTAPI)

    try:
        yield
    finally:
        logger.info('Остановка приложения %s...', config.PROJECT_NAME_FASTAPI)

        # Закрываем AuthClient.
        try:
            if hasattr(app.state, 'auth_client') and app.state.auth_client:
                await app.state.auth_client.close()
                logger.info('AuthClient закрыт')
        except Exception as e:
            logger.error('Ошибка при закрытии AuthClient: %s', e)

        # Закрываем auth-redis.
        try:
            await auth_redis_module.close_auth_redis()
            logger.info('Auth Redis закрыт')
        except Exception as e:
            logger.error('Ошибка при закрытии Auth Redis: %s', e)

        # Закрываем общий rate-limit Redis.
        try:
            await ratelimit_redis_module.close_ratelimit_redis()
            logger.info('Rate-limit Redis закрыт')
        except Exception as e:
            logger.error('Ошибка при закрытии Rate-limit Redis: %s', e)

        # Закрываем cache-redis.
        try:
            await redis.close_redis()
            logger.info('Cache Redis закрыт')
        except Exception as e:
            logger.error('Ошибка при закрытии Cache Redis: %s', e)

        # Закрываем Elasticsearch.
        try:
            await elastic.close_elastic()
            logger.info('Elasticsearch закрыт')
        except Exception as e:
            logger.error('Ошибка при закрытии Elasticsearch: %s', e)

        logger.info('Попытка закрытия подключений завершена')


# --- Создание приложения ---
app = FastAPI(
    title=config.PROJECT_NAME_FASTAPI,
    description='Сервис выдачи фильмов с интеграцией Auth-сервиса',
    version='1.0.0',
    docs_url='/api/openapi',
    redoc_url='/api/redoc',
    openapi_url='/api/openapi.json',
    lifespan=lifespan,
)

# --- Настройка трассировки (ВНЕ lifespan, до инструментации) ---
try:
    configure_tracer(service_name=config.PROJECT_NAME_FASTAPI)
    logger.info('OpenTelemetry трассировка настроена')
except Exception as e:
    logger.warning('Не удалось настроить трассировку: %s', e)

# --- Middleware ---
app.add_middleware(
    RateLimitMiddleware,
    max_requests=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_PERIOD,
)
app.add_middleware(RequestIDMiddleware)

# --- Инструментация FastAPI 
FastAPIInstrumentor.instrument_app(app)


# =============================================================================
# Централизованные обработчики исключений
# =============================================================================

@app.exception_handler(FilmNotFoundError)
async def film_not_found_handler(request: Request, exc: FilmNotFoundError):
    request_id = getattr(request.state, 'request_id', None)
    response = JSONResponse(
        status_code=404,
        content={'detail': f'Фильм {exc.film_id} не найден'},
    )
    if request_id:
        response.headers['X-Request-Id'] = request_id
    return response


@app.exception_handler(FilmDataError)
async def film_data_corrupted_handler(request: Request, exc: FilmDataError):
    request_id = getattr(request.state, 'request_id', None)
    logger.exception('Повреждённые данные фильма %s: %s', exc.film_id, exc)
    response = JSONResponse(
        status_code=500,
        content={'detail': f'Данные фильма повреждены {exc.film_id}'},
    )
    if request_id:
        response.headers['X-Request-Id'] = request_id
    return response


@app.exception_handler(IndexNotFoundError)
async def index_not_found_handler(request: Request, exc: IndexNotFoundError):
    request_id = getattr(request.state, 'request_id', None)
    logger.exception('Хранилище недоступно: индекс %s не найден', exc.index_name)
    response = JSONResponse(
        status_code=503,
        content={'detail': 'Сервис временно недоступен. Попробуйте позднее.'},
    )
    if request_id:
        response.headers['X-Request-Id'] = request_id
    return response


@app.exception_handler(ESConnectionError)
async def es_connection_error_handler(request: Request, exc: ESConnectionError):
    request_id = getattr(request.state, 'request_id', None)
    logger.exception('Elasticsearch недоступен: %s', exc)
    response = JSONResponse(
        status_code=503,
        content={'detail': 'Сервис недоступен. Попробуйте позднее.'},
    )
    if request_id:
        response.headers['X-Request-Id'] = request_id
    return response


@app.exception_handler(ConnectionTimeout)
async def es_timeout_error_handler(request: Request, exc: ConnectionTimeout):
    request_id = getattr(request.state, 'request_id', None)
    logger.exception('Превышено время ожидания ответа от Elasticsearch: %s', exc)
    response = JSONResponse(
        status_code=503,
        content={'detail': 'Сервис недоступен. Попробуйте позднее.'},
    )
    if request_id:
        response.headers['X-Request-Id'] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, 'request_id', None)
    logger.exception('Необработанная ошибка: %s', exc, exc_info=True)
    response = JSONResponse(
        status_code=500,
        content={
            'detail': 'Внутренняя ошибка сервера',
            'request_id': request_id,
        },
    )
    if request_id:
        response.headers['X-Request-Id'] = request_id
    return response


# --- Роутеры ---
app.include_router(films.router, prefix='/api/v1/films', tags=['films'])


# --- Health check эндпоинт ---
@app.get('/health', tags=['system'])
async def health_check():
    health = {
        'status': 'ok',
        'service': config.PROJECT_NAME_FASTAPI,
        'dependencies': {},
    }
    overall_ok = True

    # cache-redis
    try:
        r = redis.get_redis()
        await r.ping()
        health['dependencies']['cache_redis'] = 'ok'
    except Exception as e:
        health['dependencies']['cache_redis'] = f'degraded: {type(e).__name__}'
        overall_ok = False

    # auth-redis
    try:
        ar = getattr(app.state, 'auth_redis', None)
        if ar is None:
            raise RuntimeError('auth_redis not initialized')
        await ar.ping()
        health['dependencies']['auth_redis'] = 'ok'
    except Exception as e:
        health['dependencies']['auth_redis'] = f'degraded: {type(e).__name__}'
        overall_ok = False

    # rate-limit redis
    try:
        rr = getattr(app.state, 'ratelimit_redis', None)
        if rr is None:
            raise RuntimeError('ratelimit_redis not initialized')
        await rr.ping()
        health['dependencies']['ratelimit_redis'] = 'ok'
    except Exception as e:
        health['dependencies']['ratelimit_redis'] = f'degraded: {type(e).__name__}'
        overall_ok = False

    # Elasticsearch
    try:
        await elastic.get_elastic().info()
        health['dependencies']['elasticsearch'] = 'ok'
    except Exception as e:
        health['dependencies']['elasticsearch'] = f'degraded: {type(e).__name__}'
        overall_ok = False

    # Auth-service
    if hasattr(app.state, 'auth_client') and app.state.auth_client:
        health['dependencies']['auth_service'] = 'configured'
    else:
        health['dependencies']['auth_service'] = 'unavailable'
        overall_ok = False

    health['status'] = 'ok' if overall_ok else 'degraded'
    return health