
import logging
from uuid import UUID

from core.config import config
from core.security import TOKEN_TYPE_ACCESS, decode_token
from db.postgres import get_session
from db.redis import get_redis
from db_work.abc_rbac import RBACRepository
from db_work.abc_users import UserRepository
from db_work.postgres_rbac import PostgresRBACRepository
from db_work.postgres_users import PostgresUserRepository
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, PyJWTError
from models.auth_models import User
from redis.asyncio import Redis
from services.custom_exception import TokenError, UserNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from api.const import BLACKLIST_PREFIX, PERMS_CACHE_PREFIX

logger = logging.getLogger(__name__)


bearer_scheme = HTTPBearer(auto_error=False, description='JWT access token')


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Проверяет токен и его валидность/blacklist.
       HTTPException 401: если токен отсутствует, невалиден, истек или отозван.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Отсутствует токен',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    try:
        payload = decode_token(credentials.credentials)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Токен истёк',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Невалидный токен',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    # Проверка типа токена
    if payload.get('type') != TOKEN_TYPE_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется access-токен',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    # Проверка blacklist (logout)
    jti = payload.get('jti')
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Ошибка структуры токена',
        )

    is_blacklisted = await redis.exists(f'{BLACKLIST_PREFIX}:{jti}')
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Токен был отозван',
        )
    return payload


async def get_current_user_id(payload: dict = Depends(get_token_payload)) -> UUID:
    """Извлекает user_id из валидного payload."""
    try:
        return UUID(payload['sub'])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Некорректный формат user_id в токене',
        )


async def get_current_user(
    payload: dict = Depends(get_token_payload),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Получает объект User из БД."""
    try:
        user_id = UUID(payload['sub'])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Некорректный user_id в токене',
        )
    repo = PostgresUserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Пользователь не найден',
        )
    if int(payload.get('ver', 1)) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Сессия недействительна: пароль был изменён',
        )
    return user


def require_permission(permission_codename: str):
    """Фабрика зависимостей: возвращает асинхронный чекер."""

    async def checker(
        user: User = Depends(get_current_user),
        redis: Redis = Depends(get_redis),
        session: AsyncSession = Depends(get_session),
    ) -> User:
        if user.is_superuser:
            logger.debug('Superuser %s bypassed permission check for %s', user.login, permission_codename)
            return user

        cache_key = f'{PERMS_CACHE_PREFIX}:{user.id}'
        perms_set: set[str] | None = None

        try:
            cached_perms_json = await redis.get(cache_key)
            if cached_perms_json:
                import json
                perms_set = set(json.loads(cached_perms_json))
                logger.debug('Permissions loaded from CACHE for user %s: %s', user.id, perms_set)
        except Exception as e:
            logger.warning('Redis error while getting cache: %s', e)

        if perms_set is None:
            rbac_repo = PostgresRBACRepository(session)

            db_perms_list = await rbac_repo.get_user_permissions(user.id)
            perms_set = set(db_perms_list)

            logger.debug('Permissions loaded from DB for user %s: %s', user.id, perms_set)

            try:
                import json
                await redis.setex(
                    cache_key,
                    config.PERMS_CACHE_TTL_SECONDS,
                    json.dumps(list(perms_set)),
                )
            except Exception as e:
                logger.warning('Redis error while setting cache: %s', e)

        if permission_codename not in perms_set:
            logger.info('ACCESS DENIED: User %s lacks permission %s. Has: %s', user.id, permission_codename, perms_set)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Недостаточно прав: требуется {permission_codename}',
            )

        logger.debug('ACCESS GRANTED: User %s has permission %s', user.id, permission_codename)
        return user

    return checker


def require_role(role_name: str):
    """Фабрика зависимостей для проверки конкретной роли."""
    async def checker(
        user: User = Depends(get_current_user),
    ) -> User:
        role_names = [r.name for r in user.roles]
        if role_name not in role_names and not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Требуется роль: {role_name}',
            )
        return user
    return checker


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    redis: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Возвращает пользователя, если он авторизован, иначе None.
    """
    if credentials is None:
        return None

    try:
        payload = decode_token(credentials.credentials)
        if payload.get('type') != TOKEN_TYPE_ACCESS:
            return None

        jti = payload.get('jti')
        if await redis.exists(f'{BLACKLIST_PREFIX}:{jti}'):
            return None

        user_id = UUID(payload['sub'])
        repo = PostgresUserRepository(session)
        return await repo.get_by_id(user_id)
    except Exception:
        return None