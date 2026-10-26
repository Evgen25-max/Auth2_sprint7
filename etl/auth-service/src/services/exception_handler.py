
import logging
from functools import wraps

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from services.custom_exception import (InvalidCredentialsError,
                                       PermissionNotFoundError,
                                       RoleAlreadyExistsError,
                                       RoleNotFoundError, TokenError,
                                       UserAlreadyExistsError,
                                       UserNotFoundError)

CUSTOM_EXCEPTIONS = (
    UserAlreadyExistsError,
    InvalidCredentialsError,
    UserNotFoundError,
    TokenError,
    RoleAlreadyExistsError,
    RoleNotFoundError,
    PermissionNotFoundError,
)

logger = logging.getLogger(__name__)


def handle_storage_errors(func):
    """Логирует ошибки БД/Redis и raise.

    CUSTOM_EXCEPTIONS пропускаем без изменений,
    другие  -> 503 Service Unavailable.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except CUSTOM_EXCEPTIONS:
            raise
        except (SQLAlchemyError, RedisError) as e:
            logger.error(
                'Хранилище недоступно при вызове %s: %s',
                func.__name__, e, exc_info=True,
            )
            raise
        except Exception as e:
            logger.exception(
                'Неожиданная ошибка в %s: %s',
                func.__name__, e,
            )
            raise
    return wrapper
