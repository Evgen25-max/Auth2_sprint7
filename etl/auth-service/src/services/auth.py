
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from api.const import BLACKLIST_PREFIX, REFRESH_ACTIVE_PREFIX
from core.security import (TOKEN_TYPE_REFRESH, create_access_token,
                           create_refresh_token, decode_token, hash_password,
                           verify_password)
from db.postgres import get_session
from db.redis import get_redis
from db_work.abc_login_history import LoginHistoryRepository
from db_work.abc_rbac import RBACRepository
from db_work.abc_users import UserRepository
from db_work.postgres_login_history import PostgresLoginHistoryRepository
from db_work.postgres_rbac import PostgresRBACRepository
from db_work.postgres_users import PostgresUserRepository
from fastapi import Depends
from jwt import ExpiredSignatureError, PyJWTError
from models.token import TokenPair
from models.users import UserCreate, UserLogin, UserPublic
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from services.custom_exception import (InvalidCredentialsError, TokenError,
                                       UserAlreadyExistsError,
                                       UserNotFoundError)
from services.exception_handler import handle_storage_errors
from services.rbac import RBACService

logger = logging.getLogger(__name__)


def _get_ttl_seconds(exp_timestamp: int) -> int:
    """Вычисляет оставшееся время жизни токена в секундах."""
    now = datetime.now(timezone.utc).timestamp()
    return max(int(exp_timestamp - now), 1)


class AuthService:
    """Бизнес-логика аутентификации."""

    def __init__(
        self,
        user_repo: UserRepository,
        rbac_service: RBACService,
        history_repo: LoginHistoryRepository,
        redis: Redis,
    ):
        self._users = user_repo
        self._rbac = rbac_service
        self._history = history_repo
        self._redis = redis

    @handle_storage_errors
    async def signup(self, data: UserCreate) -> UserPublic:
        if await self._users.get_by_login(data.login):
            raise UserAlreadyExistsError(data.login)

        hashed_pw = await hash_password(data.password)

        user = await self._users.create(
            login=data.login,
            hashed_password=hashed_pw,
            first_name=data.first_name,
            last_name=data.last_name,
            is_superuser=False,
        )

        try:
            await self._rbac.assign_role_to_user(user.id, 'user', commit=False)
        except Exception as e:
            await self._session.rollback()
            logger.error('Не удалось назначить роль: %s', e)
            raise

        await self._session.commit()

        await self._session.refresh(user, ['roles'])
        logger.info('Зарегистрирован пользователь %s', user.login)
        return UserPublic.model_validate(user)

    @handle_storage_errors
    async def login(self, data: UserLogin, ip: str | None, ua: str | None) -> TokenPair:
        """Проверяет креды, пишет историю, выдает пару токенов."""
        user = await self._users.get_by_login(data.login)

        success = False
        user_id_for_history = None

        if user and await verify_password(data.password, user.hashed_password):
            success = True
            user_id_for_history = user.id

            access_token = create_access_token(str(user.id), user.is_superuser, version=user.token_version)
            refresh_token = create_refresh_token(str(user.id), user.is_superuser, version=user.token_version)

            refresh_payload = decode_token(refresh_token)
            ttl = _get_ttl_seconds(refresh_payload['exp'])
            await self._redis.setex(
                f'{REFRESH_ACTIVE_PREFIX}:{user.id}',
                ttl,
                refresh_payload['jti'],
            )

            tokens = TokenPair(access_token=access_token, refresh_token=refresh_token)
        else:
            tokens = None

        await self._history.record_login(
            user_id=user_id_for_history,
            login=data.login,
            ip_address=ip,
            user_agent=ua,
            success=success,
        )

        if not success:
            raise InvalidCredentialsError()

        return tokens

    # --- Обновление токена (Refresh) ---

    @handle_storage_errors
    async def refresh(self, refresh_token_str: str) -> TokenPair:
        """Выдает новую пару токенов по валидному refresh-токену."""
        try:
            payload = decode_token(refresh_token_str)
        except ExpiredSignatureError:
            raise TokenError('refresh token expired')
        except PyJWTError:
            raise TokenError('invalid refresh token')

        if payload.get('type') != TOKEN_TYPE_REFRESH:
            raise TokenError('wrong token type')

        jti = payload['jti']
        user_id = payload['sub']

        if await self._redis.exists(f'{BLACKLIST_PREFIX}:{jti}'):
            raise TokenError('token revoked')

        stored_jti = await self._redis.get(f'{REFRESH_ACTIVE_PREFIX}:{user_id}')
        if stored_jti != jti:
            logger.warning('Обнаружена попытка повторного использования refresh-токена для %s', user_id)
            await self._revoke_all_sessions(UUID(user_id))
            raise TokenError('refresh token rotation violation')

        user = await self._users.get_by_id(UUID(user_id))
        if user is None:
            raise UserNotFoundError(user_id)

        old_ttl = _get_ttl_seconds(payload['exp'])
        await self._redis.setex(f'{BLACKLIST_PREFIX}:{jti}', old_ttl, '1')
        new_access = create_access_token(str(user.id), user.is_superuser, version=user.token_version)
        new_refresh = create_refresh_token(str(user.id), user.is_superuser, version=user.token_version)

        new_refresh_payload = decode_token(new_refresh)
        new_ttl = _get_ttl_seconds(new_refresh_payload['exp'])

        await self._redis.setex(
            f'{REFRESH_ACTIVE_PREFIX}:{user.id}',
            new_ttl,
            new_refresh_payload['jti'],
        )

        return TokenPair(access_token=new_access, refresh_token=new_refresh)

    # --- Выход ---

    @handle_storage_errors
    async def logout(self, access_payload: dict) -> None:
        """Отозвает текущий access-токен и активный refresh-токен пользователя."""
        jti = access_payload['jti']
        user_id = access_payload['sub']

        ttl = _get_ttl_seconds(access_payload['exp'])
        await self._redis.setex(f'{BLACKLIST_PREFIX}:{jti}', ttl, '1')

        await self._redis.delete(f'{REFRESH_ACTIVE_PREFIX}:{user_id}')

        logger.info('Пользователь %s вышел из системы', user_id)

    async def _revoke_all_sessions(self, user_id: UUID) -> None:
        """Метод для отзыва всех сессий."""
        await self._redis.delete(f'{REFRESH_ACTIVE_PREFIX}:{str(user_id)}')


    @handle_storage_errors
    async def get_me(self, user_id: UUID) -> UserPublic:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))
        return UserPublic.model_validate(user)

    @handle_storage_errors
    async def update_profile(
        self,
        user_id: UUID,
        current_password: str | None = None,
        login: str | None = None,
        password: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> UserPublic:
        """Обновляет данные профиля."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))
        sensitive_change = (
            (login is not None and login != user.login)
            or password is not None
        )
        if sensitive_change:
            if not current_password:
                raise InvalidCredentialsError()
            if not await verify_password(current_password, user.hashed_password):
                raise InvalidCredentialsError()

        if login and login != user.login:
            if await self._users.get_by_login(login):
                raise UserAlreadyExistsError(login)
            user.login = login

        if password:
            user.hashed_password = await hash_password(password)
        user.token_version += 1
        await self._redis.delete(f'{REFRESH_ACTIVE_PREFIX}:{user.id}')

        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name

        await self._session.commit()
        await self._session.refresh(user)
        return UserPublic.model_validate(user)

    @property
    def _session(self) -> AsyncSession:
        return self._users._session

    @handle_storage_errors
    async def get_login_history(self, user_id: UUID, limit: int = 20) -> list:
        """Возвращает историю входов пользователя."""
        return await self._history.get_recent_logins(user_id, limit=limit)


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> AuthService:
    """DI Factory для AuthService."""
    user_repo = PostgresUserRepository(session)
    rbac_repo = PostgresRBACRepository(session)
    history_repo = PostgresLoginHistoryRepository(session)

    rbac_service = RBACService(repo=rbac_repo, redis=redis, session=session)

    return AuthService(
        user_repo=user_repo,
        rbac_service=rbac_service,
        history_repo=history_repo,
        redis=redis,
    )

