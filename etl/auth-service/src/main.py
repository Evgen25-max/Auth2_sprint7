
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from services.seed import seed_system_data
from db.postgres import async_session
from api.v1 import auth, roles, social, users, internal
from core.config import config
from core.logger import LOGGING
from db import postgres, redis
from db import ratelimit_redis as ratelimit_redis_module
from middleware.rate_limit import RateLimitMiddleware
from middleware.request_id import RequestIDMiddleware
from services.custom_exception import (
    AccountLockedError,
    CannotUnlinkLastAuthMethodError,
    InvalidCredentialsError,
    MergeRequiresPasswordError,
    MergeWithSelfError,
    OAuthProviderError,
    OAuthStateError,
    PermissionNotFoundError,
    RoleAlreadyExistsError,
    RoleNotFoundError,
    SocialAccountAlreadyLinkedError,
    SocialAccountLinkedToAnotherUserError,
    SocialAccountNotLinkedError,
    TokenError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from tracing import configure_tracer

logging.config.dictConfig(LOGGING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    logger.info('Запуск приложения %s...', config.PROJECT_NAME)

    redis.init_redis()

    try:
        await postgres.check_postgres()
        logger.info('PostgreSQL доступен')
    except Exception as exc:
        logger.exception('PostgreSQL недоступен при старте')
        raise RuntimeError('PostgreSQL unavailable at startup') from exc

    try:
        await redis.get_redis().ping()
        logger.info('Auth Redis доступен')
    except Exception as exc:
        logger.exception('Auth Redis недоступен при старте')
        raise RuntimeError('Auth Redis unavailable at startup') from exc

    if config.RATE_LIMIT_ENABLED:
        try:
            ratelimit_redis_module.init_ratelimit_redis()
            rl = ratelimit_redis_module.get_ratelimit_redis()
            await rl.ping()
            app.state.ratelimit_redis = rl
            logger.info('Rate-limit Redis доступен')
        except Exception as exc:
            logger.exception('Rate-limit Redis недоступен при старте')
            raise RuntimeError('Rate-limit Redis unavailable at startup') from exc
    else:
        app.state.ratelimit_redis = None
        logger.info('Rate limiting отключён конфигурацией')

    try:
        async with async_session() as session:
            await seed_system_data(session)
        logger.info('Системные роли и права инициализированы')
    except Exception as exc:
        logger.exception('Ошибка инициализации системных ролей и прав')
        raise RuntimeError('Failed to seed system roles and permissions') from exc

    logger.info('Приложение запущено')

    try:
        yield
    finally:
        logger.info('Остановка приложения')

        if config.RATE_LIMIT_ENABLED:
            try:
                await ratelimit_redis_module.close_ratelimit_redis()
                logger.info('Rate-limit Redis закрыт')
            except Exception as exc:
                logger.error('Ошибка при закрытии Rate-limit Redis: %s', exc)

        try:
            await redis.close_redis()
        except Exception as exc:
            logger.error('Ошибка при закрытии Redis: %s', exc)

        try:
            await postgres.close_postgres()
        except Exception as exc:
            logger.error('Ошибка при закрытии PostgreSQL: %s', exc)


try:
    configure_tracer(service_name=config.PROJECT_NAME)
    logger.info('OpenTelemetry трассировка настроена')
except Exception as e:
    logger.warning('Не удалось настроить трассировку: %s', e)


app = FastAPI(
    title=config.PROJECT_NAME,
    version='1.0.0',
    docs_url='/api/v1/auth/docs',
    redoc_url='/api/v1/auth/redoc',
    openapi_url='/api/v1/auth/openapi.json',
    lifespan=lifespan,
)

app.add_middleware(
    RateLimitMiddleware,
    enabled=config.RATE_LIMIT_ENABLED,
    max_requests=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_PERIOD,
)
app.add_middleware(RequestIDMiddleware)

FastAPIInstrumentor.instrument_app(app)


# --- обработчики исключений ---

def _json_response_with_request_id(request: Request, status_code: int, exc: Exception):
    request_id = getattr(request.state, 'request_id', None)
    response = JSONResponse(status_code=status_code, content={'detail': str(exc)})
    if request_id:
        response.headers['X-Request-Id'] = request_id
    return response


@app.exception_handler(AccountLockedError)
async def account_locked_handler(request: Request, exc: AccountLockedError):
    logger.warning('Заблокированный вход: login=%s', exc.login)
    return _json_response_with_request_id(request, 423, exc)


@app.exception_handler(UserAlreadyExistsError)
async def user_exists_handler(request: Request, exc: UserAlreadyExistsError):
    return _json_response_with_request_id(request, 409, exc)


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError):
    return _json_response_with_request_id(request, 401, exc)


@app.exception_handler(UserNotFoundError)
async def user_not_found_handler(request: Request, exc: UserNotFoundError):
    return _json_response_with_request_id(request, 404, exc)


@app.exception_handler(TokenError)
async def token_error_handler(request: Request, exc: TokenError):
    return _json_response_with_request_id(request, 401, exc)


@app.exception_handler(RoleAlreadyExistsError)
async def role_exists_handler(request: Request, exc: RoleAlreadyExistsError):
    return _json_response_with_request_id(request, 409, exc)


@app.exception_handler(RoleNotFoundError)
async def role_not_found_handler(request: Request, exc: RoleNotFoundError):
    return _json_response_with_request_id(request, 404, exc)


@app.exception_handler(PermissionNotFoundError)
async def perm_not_found_handler(request: Request, exc: PermissionNotFoundError):
    return _json_response_with_request_id(request, 404, exc)


# --- OAuth / Social обработчики ---

@app.exception_handler(OAuthStateError)
async def oauth_state_error_handler(request: Request, exc: OAuthStateError):
    return _json_response_with_request_id(request, 400, exc)


@app.exception_handler(OAuthProviderError)
async def oauth_provider_error_handler(request: Request, exc: OAuthProviderError):
    logger.warning('Ошибка OAuth-провайдера: %s', exc.detail)
    return _json_response_with_request_id(request, 502, exc)


@app.exception_handler(SocialAccountAlreadyLinkedError)
async def social_already_linked_handler(request: Request, exc: SocialAccountAlreadyLinkedError):
    return _json_response_with_request_id(request, 409, exc)


@app.exception_handler(SocialAccountLinkedToAnotherUserError)
async def social_linked_to_another_handler(request: Request, exc: SocialAccountLinkedToAnotherUserError):
    return _json_response_with_request_id(request, 409, exc)


@app.exception_handler(SocialAccountNotLinkedError)
async def social_not_linked_handler(request: Request, exc: SocialAccountNotLinkedError):
    return _json_response_with_request_id(request, 404, exc)


@app.exception_handler(CannotUnlinkLastAuthMethodError)
async def cannot_unlink_last_handler(request: Request, exc: CannotUnlinkLastAuthMethodError):
    return _json_response_with_request_id(request, 409, exc)


@app.exception_handler(MergeRequiresPasswordError)
async def merge_requires_password_handler(request: Request, exc: MergeRequiresPasswordError):
    return _json_response_with_request_id(request, 409, exc)


@app.exception_handler(MergeWithSelfError)
async def merge_with_self_handler(request: Request, exc: MergeWithSelfError):
    return _json_response_with_request_id(request, 409, exc)


@app.exception_handler(RedisError)
@app.exception_handler(SQLAlchemyError)
async def storage_unavailable_handler(request: Request, exc: Exception):
    logger.exception('Хранилище недоступно: %s', exc)
    return _json_response_with_request_id(
        request, 503,
        Exception('Сервис временно недоступен. Попробуйте позднее.'),
    )


app.include_router(auth.router, prefix='/api/v1')
app.include_router(users.router, prefix='/api/v1')
app.include_router(roles.router, prefix='/api/v1')
app.include_router(social.router, prefix='/api/v1')
app.include_router(internal.router, prefix='/api/v1')