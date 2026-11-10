
import json
import logging
import secrets
from uuid import UUID

from api.const import (
    OAUTH_STATE_PREFIX,
    OAUTH_STATE_TTL,
    PERMS_CACHE_PREFIX,
    REFRESH_ACTIVE_PREFIX,
    USER_VER_PREFIX,
)
from core.security import verify_password
from db.postgres import get_session
from db.redis import get_redis
from db_work.abc_login_history import LoginHistoryRepository
from db_work.abc_rbac import RBACRepository
from db_work.abc_social import SocialAccountRepository
from db_work.abc_users import UserRepository
from db_work.postgres_login_history import PostgresLoginHistoryRepository
from db_work.postgres_rbac import PostgresRBACRepository
from db_work.postgres_social import PostgresSocialAccountRepository
from db_work.postgres_users import PostgresUserRepository
from fastapi import Depends
from models.auth_models import User
from models.social import SocialAccountPublic
from models.token import TokenPair
from models.users import UserPublic
from oauth.registry import get_provider
from oauth.schemas import SocialUserInfo
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth import issue_token_pair
from services.custom_exception import (
    CannotUnlinkLastAuthMethodError,
    InvalidCredentialsError,
    MergeRequiresPasswordError,
    MergeWithSelfError,
    OAuthProviderError,
    OAuthStateError,
    SocialAccountAlreadyLinkedError,
    SocialAccountLinkedToAnotherUserError,
    SocialAccountNotLinkedError,
    UserNotFoundError,
)
from services.exception_handler import handle_storage_errors
from services.rbac import RBACService
from core.tracing_decorators import traced

logger = logging.getLogger(__name__)

_PURPOSE_LOGIN = 'login'
_PURPOSE_LINK = 'link'
_PURPOSE_MERGE = 'merge'


class SocialAuthService:
    """
    Бизнес-логика входа, привязки, отвязки и объединения
    аккаунтов через социальные сети.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        social_repo: SocialAccountRepository,
        rbac_service: RBACService,
        history_repo: LoginHistoryRepository,
        redis: Redis,
    ):
        self._users = user_repo
        self._social = social_repo
        self._rbac = rbac_service
        self._history = history_repo
        self._redis = redis

    @property
    def _session(self) -> AsyncSession:
        return self._users._session

    # ------------------------------------------------------------------
    # OAuth state (CSRF-защита + привязка операции к пользователю)
    # ------------------------------------------------------------------

    async def _create_state(self, purpose: str, user_id: UUID | None) -> str:
        state = secrets.token_urlsafe(32)
        payload = {
            'purpose': purpose,
            'user_id': str(user_id) if user_id else None,
        }
        await self._redis.setex(
            f'{OAUTH_STATE_PREFIX}:{state}',
            OAUTH_STATE_TTL,
            json.dumps(payload),
        )
        return state

    async def _consume_state(
        self,
        state: str,
        expected_purpose: str,
        expected_user_id: UUID | None = None,
    ) -> None:
        """Проверяет и сразу удаляет state (одноразовый)."""
        key = f'{OAUTH_STATE_PREFIX}:{state}'
        try:
            raw = await self._redis.get(key)
            if raw is None:
                raise OAuthStateError()
            await self._redis.delete(key)
        except RedisError as e:
            logger.error('Redis недоступен при проверке OAuth state: %s', e)
            raise OAuthStateError()

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raise OAuthStateError()

        if data.get('purpose') != expected_purpose:
            raise OAuthStateError()

        if expected_user_id is not None:
            if data.get('user_id') != str(expected_user_id):
                raise OAuthStateError()

    # ------------------------------------------------------------------
    # Вспомогательные
    # ------------------------------------------------------------------
    @traced(
        name="SocialAuthService.get_authorize_url",
        allow_fields={"provider_name", "purpose", "user_id", "redirect_uri"},
    )
    async def get_authorize_url(
        self,
        provider_name: str,
        purpose: str,
        user_id: UUID | None = None,
        redirect_uri: str | None = None,
    ) -> dict:
        """
        Возвращает ссылку на страницу авторизации провайдера и state.
        purpose: login | link | merge.
        """
        if purpose not in (_PURPOSE_LOGIN, _PURPOSE_LINK, _PURPOSE_MERGE):
            raise OAuthStateError()
        if purpose in (_PURPOSE_LINK, _PURPOSE_MERGE) and user_id is None:
            raise OAuthStateError()

        provider = get_provider(provider_name)
        state = await self._create_state(purpose, user_id)
        auth_url = provider.get_auth_url(state=state, redirect_uri=redirect_uri)
        return {'auth_url': auth_url, 'state': state}

    async def _fetch_social_user(
        self, provider_name: str, code: str
    ) -> SocialUserInfo:
        provider = get_provider(provider_name)
        token_data = await provider.exchange_code(code)
        access_token = token_data.get('access_token')
        if not access_token:
            raise OAuthProviderError('Провайдер не вернул access_token')
        return await provider.fetch_user_info(access_token)

    # ------------------------------------------------------------------
    # Вход через соцсеть
    # ------------------------------------------------------------------
    @traced(
        name="SocialAuthService.oauth_login",
        allow_fields={"provider_name"},
    )
    @handle_storage_errors
    async def oauth_login(
        self,
        provider_name: str,
        code: str,
        state: str,
        ip: str | None,
        ua: str | None,
    ) -> TokenPair:
        """Вход/регистрация через соцсеть."""
        await self._consume_state(state, _PURPOSE_LOGIN)
        info = await self._fetch_social_user(provider_name, code)
        user = await self._resolve_user_for_login(provider_name, info)

        await self._history.record_login(
            user_id=user.id,
            login=f'{provider_name}:{info.external_id}',
            ip_address=ip,
            user_agent=ua,
            success=True,
        )

        await self._publish_token_version(user.id, user.token_version)
        return await issue_token_pair(user, self._redis)

    async def _resolve_user_for_login(
        self, provider_name: str, info: SocialUserInfo
    ) -> User:
        """
        Сценарии:
          А. Привязка уже есть — возвращаем её пользователя.
          Б. Привязки нет, но найден пользователь по доверенному email —
             привязываем соцсеть к нему (автосвязывание).
          В. Ничего не найдено — создаём нового пользователя.
        """
        # А. Существующая привязка
        link = await self._social.get_link(provider_name, info.external_id)
        if link is not None:
            user = await self._users.get_by_id(link.user_id)
            if user is not None:
                return user

        # Б. Автосвязывание по доверенному email
        if info.email:
            user = await self._users.get_by_email(info.email)
            if user is not None:
                await self._social.create_link(
                    user_id=user.id,
                    provider=provider_name,
                    external_id=info.external_id,
                    email=info.email,
                    phone=info.phone,
                    username=info.username,
                    avatar_url=info.avatar_url,
                    raw_data=info.raw,
                )
                await self._session.commit()
                logger.info(
                    'Соцсеть %s автосвязана с пользователем %s по email',
                    provider_name, user.id,
                )
                return user

        # В. Новый пользователь
        user = await self._users.create_oauth_user(
            login=f'{provider_name}_{info.external_id}',
            email=info.email,
            first_name=info.first_name,
            last_name=info.last_name,
        )
        await self._social.create_link(
            user_id=user.id,
            provider=provider_name,
            external_id=info.external_id,
            email=info.email,
            phone=info.phone,
            username=info.username,
            avatar_url=info.avatar_url,
            raw_data=info.raw,
        )
        await self._rbac.assign_role_to_user(user.id, 'user', commit=False)
        await self._session.commit()
        await self._session.refresh(user, ['roles'])
        logger.info(
            'Создан пользователь %s через %s', user.login, provider_name
        )
        return user

    # ------------------------------------------------------------------
    # Привязка соцсети к текущему аккаунту
    # ------------------------------------------------------------------
    @traced(
        name="SocialAuthService.link_social",
        allow_fields={"provider_name", "user_id"},
    )
    @handle_storage_errors
    async def link_social(
        self,
        user_id: UUID,
        provider_name: str,
        code: str,
        state: str,
    ) -> SocialAccountPublic:
        await self._consume_state(state, _PURPOSE_LINK, user_id)
        info = await self._fetch_social_user(provider_name, code)

        existing = await self._social.get_link(provider_name, info.external_id)
        if existing is not None:
            if existing.user_id == user_id:
                raise SocialAccountAlreadyLinkedError(provider_name)
            raise SocialAccountLinkedToAnotherUserError(provider_name)

        link = await self._social.create_link(
            user_id=user_id,
            provider=provider_name,
            external_id=info.external_id,
            email=info.email,
            phone=info.phone,
            username=info.username,
            avatar_url=info.avatar_url,
            raw_data=info.raw,
        )

        # Если у пользователя ещё не было доверенного email — заполняем.
        user = await self._users.get_by_id(user_id)
        if user is not None and not user.email and info.email:
            user.email = info.email

        await self._session.commit()
        logger.info('Пользователь %s привязал соцсеть %s', user_id, provider_name)
        return SocialAccountPublic.model_validate(link)

    # ------------------------------------------------------------------
    # Открепление соцсети
    # ------------------------------------------------------------------
    @traced(
        name="SocialAuthService.unlink_social",
        allow_fields={"user_id", "provider_name"},
    )
    @handle_storage_errors
    async def unlink_social(self, user_id: UUID, provider_name: str) -> None:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))

        link = await self._social.get_link_for_user(user_id, provider_name)
        if link is None:
            raise SocialAccountNotLinkedError(provider_name)

        has_password = bool(user.hashed_password)
        other_links_count = await self._social.count_links(
            user_id, exclude_provider=provider_name
        )

        if not has_password and other_links_count == 0:
            raise CannotUnlinkLastAuthMethodError()

        await self._social.delete_link(user_id, provider_name)
        await self._session.commit()
        logger.info('Пользователь %s отвязал соцсеть %s', user_id, provider_name)

    # ------------------------------------------------------------------
    # Ручное объединение аккаунтов
    # ------------------------------------------------------------------
    @traced(
        name="SocialAuthService.merge_accounts",
        allow_fields={"provider_name", "user_id"},
    )
    @handle_storage_errors
    async def merge_accounts(
        self,
        user_id: UUID,
        provider_name: str,
        code: str,
        state: str,
        merge_password: str | None = None,
    ) -> UserPublic:
        """
        Объединяет аккаунт, найденный по соцсети, с текущим аккаунтом.
        """
        await self._consume_state(state, _PURPOSE_MERGE, user_id)
        info = await self._fetch_social_user(provider_name, code)

        link = await self._social.get_link(provider_name, info.external_id)
        if link is None:
            raise SocialAccountNotLinkedError(provider_name)

        source_user_id = link.user_id
        if source_user_id == user_id:
            raise MergeWithSelfError()

        target = await self._users.get_by_id(user_id)
        source = await self._users.get_by_id(source_user_id)
        if target is None:
            raise UserNotFoundError(str(user_id))
        if source is None:
            raise UserNotFoundError(str(source_user_id))

        # Если присоединяемый аккаунт защищён паролем — подтверждаем его.
        if source.hashed_password:
            if not merge_password:
                raise MergeRequiresPasswordError()
            if not await verify_password(merge_password, source.hashed_password):
                raise InvalidCredentialsError()

        # Перенос привязок и истории входов на целевой аккаунт.
        await self._social.reassign_links(from_user_id=source.id, to_user_id=target.id)
        await self._social.reassign_login_history(from_user_id=source.id, to_user_id=target.id)

        # Если у целевого юзера нет доверенного email, а у источника есть — переносим.
        if not target.email and source.email:
            target.email = source.email

        # Удаляем присоединённый аккаунт.
        await self._users.delete(source.id)
        await self._session.commit()

        # Инвалидируем токены удалённого аккаунта во всех сервисах.
        await self._invalidate_user_sessions(source.id, source.token_version)

        logger.info(
            'Аккаунт %s объединён с аккаунтом %s', source.id, user_id
        )

        fresh_target = await self._users.get_by_id(user_id)
        return UserPublic.model_validate(fresh_target)

    async def _invalidate_user_sessions(self, user_id: UUID, token_version: int) -> None:
        """Инвалидирует сессии пользователя во всех сервисах через Redis."""
        try:
            await self._redis.set(
                f'{USER_VER_PREFIX}:{user_id}', str(token_version + 1)
            )
            await self._redis.delete(f'{REFRESH_ACTIVE_PREFIX}:{user_id}')
            await self._redis.delete(f'{PERMS_CACHE_PREFIX}:{user_id}')
        except RedisError as e:
            logger.error(
                'Не удалось инвалидировать сессии пользователя %s: %s', user_id, e
            )

    # ------------------------------------------------------------------
    # Список привязанных соцсетей
    # ------------------------------------------------------------------
    @traced(
        name="SocialAuthService.get_linked_accounts",
        allow_fields={"user_id"},
    )
    @handle_storage_errors
    async def get_linked_accounts(self, user_id: UUID) -> list[SocialAccountPublic]:
        links = await self._social.get_links_by_user(user_id)
        return [SocialAccountPublic.model_validate(link) for link in links]

    # ------------------------------------------------------------------
    # Публикация версии токена
    # ------------------------------------------------------------------

    async def _publish_token_version(self, user_id: UUID, version: int) -> None:
        try:
            await self._redis.set(f'{USER_VER_PREFIX}:{user_id}', str(version))
        except RedisError as e:
            logger.error(
                'Не удалось опубликовать user_ver для %s: %s', user_id, e
            )


async def get_social_service(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> SocialAuthService:
    """DI Factory для SocialAuthService."""
    user_repo = PostgresUserRepository(session)
    social_repo = PostgresSocialAccountRepository(session)
    rbac_repo = PostgresRBACRepository(session)
    history_repo = PostgresLoginHistoryRepository(session)

    rbac_service = RBACService(repo=rbac_repo, redis=redis, session=session)

    return SocialAuthService(
        user_repo=user_repo,
        social_repo=social_repo,
        rbac_service=rbac_service,
        history_repo=history_repo,
        redis=redis,
    )