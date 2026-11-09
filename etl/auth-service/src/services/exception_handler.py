
import logging
from functools import wraps

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

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

CUSTOM_EXCEPTIONS = (
    AccountLockedError,
    UserAlreadyExistsError,
    InvalidCredentialsError,
    UserNotFoundError,
    TokenError,
    RoleAlreadyExistsError,
    RoleNotFoundError,
    PermissionNotFoundError,
    OAuthProviderError,
    OAuthStateError,
    SocialAccountAlreadyLinkedError,
    SocialAccountLinkedToAnotherUserError,
    SocialAccountNotLinkedError,
    CannotUnlinkLastAuthMethodError,
    MergeRequiresPasswordError,
    MergeWithSelfError,
)

logger = logging.getLogger(__name__)


def handle_storage_errors(func):
    """
    Логирует ошибки БД/Redis и пробрасывает их дальше.
    CUSTOM_EXCEPTIONS не трогаем.
    SQLAlchemyError / RedisError приводят к 503 через обработчик в main.py.
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
            logger.exception('Неожиданная ошибка в %s: %s', func.__name__, e)
            raise

    return wrapper