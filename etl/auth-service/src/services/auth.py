
import logging
from datetime import datetime, timezone
from uuid import UUID

from api.const import (
    BLACKLIST_PREFIX,
    FAILED_ATTEMPTS_PREFIX,
    LOCKOUT_PREFIX,
    REFRESH_ACTIVE_PREFIX,
    USER_VER_PREFIX,
)
from core.config import config
from core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
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
from models.auth_models import User
from models.token import TokenPair
from models.users import UserCreate, UserLogin, UserPublic
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from services.custom_exception import (
    AccountLockedError,
    InvalidCredentialsError,
    TokenError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from services.exception_handler import handle_storage_errors
from services.rbac import RBACService
from core.tracing_decorators import traced

logger = logging.getLogger(__name__)


def _get_ttl_seconds(exp_timestamp: int) -> int:
    """Вычисляет оставшееся время жизни токена в секундах."""
    now = datetime.now(timezone.utc).timestamp()
    return max(int(exp_timestamp - now), 1)


async def issue_token_pair(user: User, redis: Redis) -> TokenPair:
    """
    Выдаёт пару JWT-токенов для пользователя и фиксирует refresh в Redis.
    """
    access_token = create_access_token(
        str(user.id), user.is_superuser, version=user.token_version
    )
    refresh_token = create_refresh_token(
        str(user.id), user.is_superuser, version=user.token_version
    )
    refresh_payload = decode_token(refresh_token)
    ttl = _get_ttl_seconds(refresh_payload['exp'])
    await redis.setex(
        f'{REFRESH_ACTIVE_PREFIX}:{user.id}',
        ttl,
        refresh_payload['jti'],
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


_FAILED_ATTEMPTS_LUA = """
local failed_key = KEYS[1]
local lockout_key = KEYS[2]
local threshold = tonumber(ARGV[1])
local window_sec = tonumber(ARGV[2])
local lockout_sec = tonumber(ARGV[3])
local n = redis.call('INCR', failed_key)
if n == 1 then
    redis.call('EXPIRE', failed_key, window_sec)
end
if n >= threshold then
    redis.call('SETEX', lockout_key, lockout_sec, '1')
    redis.call('DEL', failed_key)
    return 2
end
return 1
"""


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

    @property
    def _session(self) -> AsyncSession:
        return self._users._session

    @property
    def rbac(self) -> RBACService:
        return self._rbac

    # ------------------------------------------------------------------
    # Lockout helpers
    # ------------------------------------------------------------------

    async def _is_locked_out(self, user_id: UUID) -> bool:
        return bool(await self._redis.exists(f'{LOCKOUT_PREFIX}:{user_id}'))

    async def _register_failed_attempt(self, user_id: UUID) -> None:
        failed_key = f'{FAILED_ATTEMPTS_PREFIX}:{user_id}'
        lockout_key = f'{LOCKOUT_PREFIX}:{user_id}'
        await self._redis.eval(
            _FAILED_ATTEMPTS_LUA,
            2,
            failed_key,
            lockout_key,
            config.LOGIN_FAILED_THRESHOLD,
            config.LOGIN_FAILED_WINDOW_SEC,
            config.LOGIN_LOCKOUT_SEC,
        )

    async def _clear_failed_attempts(self, user_id: UUID) -> None:
        await self._redis.delete(
            f'{FAILED_ATTEMPTS_PREFIX}:{user_id}',
            f'{LOCKOUT_PREFIX}:{user_id}',
        )

    async def _publish_token_version(self, user_id: UUID, version: int) -> None:
        try:
            await self._redis.set(f'{USER_VER_PREFIX}:{user_id}', str(version))
            logger.info('Опубликован user_ver=%s для пользователя %s', version, user_id)
        except RedisError as e:
            logger.error(
                'Не удалось опубликовать user_ver для %s после commit: %s',
                user_id, e,
            )

    # ------------------------------------------------------------------
    # Signup
    # ------------------------------------------------------------------
    @traced(name="AuthService.signup", allow_fields={"first_name", "last_name"})
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
        except Exception:
            await self._session.rollback()
            logger.exception('Не удалось назначить роль user пользователю %s', user.login)
            raise

        await self._session.commit()
        await self._session.refresh(user, ['roles'])
        logger.info('Зарегистрирован пользователь %s', user.login)
        return UserPublic.model_validate(user)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    @traced(name="AuthService.login", allow_fields=set(),)
    @handle_storage_errors
    async def login(self, data: UserLogin, ip: str | None, ua: str | None) -> TokenPair:
        user = await self._users.get_by_login(data.login)

        if user and await self._is_locked_out(user.id):
            logger.warning(
                'Попытка входа в заблокированный аккаунт: login=%s ip=%s ua=%s',
                data.login, ip, ua,
            )
            raise AccountLockedError(data.login)

        success = False
        user_id_for_history: UUID | None = None
        tokens: TokenPair | None = None

        if user and user.hashed_password and await verify_password(data.password, user.hashed_password):
            success = True
            user_id_for_history = user.id
            await self._clear_failed_attempts(user.id)
            tokens = await issue_token_pair(user, self._redis)
            await self._publish_token_version(user.id, user.token_version)
        else:
            if user:
                await self._register_failed_attempt(user.id)

        await self._history.record_login(
            user_id=user_id_for_history,
            login=data.login,
            ip_address=ip,
            user_agent=ua,
            success=success,
        )

        if not success:
            raise InvalidCredentialsError()

        if tokens is None:
            raise InvalidCredentialsError()

        return tokens

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    @traced(name="AuthService.refresh", allow_fields=set())
    @handle_storage_errors
    async def refresh(self, refresh_token_str: str) -> TokenPair:
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
            logger.warning(
                'Обнаружена попытка повторного использования refresh-токена для %s',
                user_id,
            )
            await self._revoke_all_sessions(UUID(user_id))
            raise TokenError('refresh token rotation violation')

        user = await self._users.get_by_id(UUID(user_id))
        if user is None:
            raise UserNotFoundError(user_id)

        try:
            token_ver = int(payload.get('ver', 1))
            current_ver = int(user.token_version)
        except (TypeError, ValueError):
            raise TokenError('invalid token version')

        if token_ver < current_ver:
            raise TokenError('refresh token version stale')

        old_ttl = _get_ttl_seconds(payload['exp'])
        await self._redis.setex(f'{BLACKLIST_PREFIX}:{jti}', old_ttl, '1')

        tokens = await issue_token_pair(user, self._redis)
        return tokens

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    @traced(name="AuthService.logout", allow_fields=set(),)
    @handle_storage_errors
    async def logout(self, access_payload: dict) -> None:
        jti = access_payload['jti']
        user_id = access_payload['sub']

        ttl = _get_ttl_seconds(access_payload['exp'])
        await self._redis.setex(f'{BLACKLIST_PREFIX}:{jti}', ttl, '1')
        await self._redis.delete(f'{REFRESH_ACTIVE_PREFIX}:{user_id}')

        logger.info('Пользователь %s вышел из системы', user_id)

    async def _revoke_all_sessions(self, user_id: UUID) -> None:
        await self._redis.delete(f'{REFRESH_ACTIVE_PREFIX}:{str(user_id)}')

    # ------------------------------------------------------------------
    # Me
    # ------------------------------------------------------------------
    @traced(name="AuthService.get_me", allow_fields=set(),)
    @handle_storage_errors
    async def get_me(self, user_id: UUID) -> UserPublic:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))
        return UserPublic.model_validate(user)

    # ------------------------------------------------------------------
    # Update profile  ← ГЛАВНОЕ ИСПРАВЛЕНИЕ ЗДЕСЬ
    # ------------------------------------------------------------------
    @traced(name="AuthService.update_profile", allow_fields={"login", "first_name", "last_name"},)
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
        """
        Обновляет профиль пользователя.

        Правила:
        - Смена логина/установка нового пароля — sensitive change.
        - Смена имени/фамилии — НЕ sensitive, current_password не нужен.
        - Если у пользователя УЖЕ есть пароль — требуется current_password.
        - Если у пользователя НЕТ пароля (OAuth-only) — разрешаем установку
          первого пароля без current_password. Это нужно, чтобы OAuth-юзер
          мог задать пароль и потом отвязать соцсеть.
        """
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))

        sensitive_change = (
            (login is not None and login != user.login)
            or password is not None
        )

        if sensitive_change:
            has_password = bool(user.hashed_password)

            if has_password:
                # У пользователя уже есть пароль — требуем подтверждение.
                if not current_password:
                    raise InvalidCredentialsError()
                if not await verify_password(current_password, user.hashed_password):
                    raise InvalidCredentialsError()
            else:
                # OAuth-only пользователь без пароля.
                # Разрешаем установку ПЕРВОГО пароля и/или смену логина
                if current_password:
                    logger.debug(
                        'current_password передан для OAuth-only пользователя %s — игнорируем',
                        user.id,
                    )

        # Обновляем логин
        if login and login != user.login:
            if await self._users.get_by_login(login):
                raise UserAlreadyExistsError(login)
            user.login = login

        # Обновляем пароль
        if password:
            user.hashed_password = await hash_password(password)

        # Обновляем имя/фамилию
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name

        # Инвалидируем сессии только при чувствительных изменениях
        if sensitive_change:
            user.token_version += 1
            await self._redis.delete(f'{REFRESH_ACTIVE_PREFIX}:{user.id}')

        await self._session.commit()
        await self._session.refresh(user)

        # Публикуем новую версию токенов после успешного commit
        if sensitive_change:
            await self._publish_token_version(user.id, user.token_version)

        return UserPublic.model_validate(user)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    @traced(name="AuthService.get_login_history", allow_fields=set(),)
    @handle_storage_errors
    async def get_login_history(self, user_id: UUID, limit: int = 20) -> list:
        return await self._history.get_recent_logins(user_id, limit=limit)


@traced(name="AuthService.get_auth_service", allow_fields=set(),)
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