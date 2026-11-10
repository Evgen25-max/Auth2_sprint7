
import json
import logging
from functools import lru_cache
from typing import Optional
from uuid import UUID

import httpx
import jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError
from core.config import config
from core.auth_keys import (
    BLACKLIST_PREFIX,
    PERMS_CACHE_PREFIX,
    USER_VER_PREFIX,
)
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)
propagator = TraceContextTextMapPropagator()
tracer = trace.get_tracer(__name__)


class AuthClient:
    """
    HTTP-клиент для обращения к Auth-сервису.
    """

    def __init__(self, base_url: str, timeout: float = 3.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def validate_token(self, token: str) -> Optional[dict]:
        """
        Проверяет токен через Auth-сервис.
        """
        with tracer.start_as_current_span('AuthClient.validate_token'):
            try:
                client = await self._get_client()

                headers = {}
                propagator.inject(headers)
                headers['Authorization'] = f'Bearer {token}'

                response = await client.post(
                    '/api/v1/auth/validate',
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('valid') and data.get('type') == 'access':
                        return data

                    logger.warning('Auth вернул valid=False или не access token')
                    return None

                logger.warning('Auth вернул статус %s', response.status_code)
                return None

            except Exception as e:
                logger.warning('Auth-сервис недоступен при удалённой проверке: %s', e)
                return None

    async def get_permissions(self, user_id: UUID) -> Optional[set[str]]:
        """
        Получает права пользователя через Auth-сервис.

        ВАЖНО:
            Текущий endpoint:
                GET /api/v1/internal/users/{user_id}/permissions
            Защищён служебным ключом X-Internal-Key.
        """
        with tracer.start_as_current_span('AuthClient.get_permissions'):
            try:
                client = await self._get_client()

                headers = {
                    'X-Internal-Key': config.INTERNAL_API_KEY,
                }
                propagator.inject(headers)

                response = await client.get(
                    f'/api/v1/internal/users/{user_id}/permissions',
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    return set(data.get('permissions', []))

                logger.warning(
                    'Auth вернул статус %s при получении прав для %s',
                    response.status_code,
                    user_id,
                )
                return None
            except Exception as e:
                logger.error('Ошибка получения прав: %s', e)
                return None


class TokenVerifier:
    """
    Локальная проверка JWT против auth-redis.

    Порядок:
      1. Локальная проверка подписи JWT.
      2. Проверка типа access.
      3. Проверка blacklist: auth:blacklist:{jti}.
      4. Проверка версии токена: auth:user_ver:{user_id}.
    """

    def __init__(
        self,
        auth_redis: Optional[Redis],
        auth_client: Optional[AuthClient] = None,
    ):
        self.auth_redis = auth_redis
        self.auth_client = auth_client
        self.secret_key = config.JWT_SECRET_KEY
        self.algorithm = config.JWT_ALGORITHM
        self.perms_ttl = config.PERMS_CACHE_TTL_SECONDS

    async def verify_token(self, token: str) -> Optional[dict]:
        """
        Возвращает payload, если токен валиден и не отозван.
        """
        with tracer.start_as_current_span('TokenVerifier.verify_token') as span:
            # 1. Локальная проверка подписи.
            try:
                payload = jwt.decode(
                    token,
                    self.secret_key,
                    algorithms=[self.algorithm],
                )
            except jwt.ExpiredSignatureError:
                span.set_attribute('auth.result', 'expired')
                logger.debug('Токен истёк')
                return None
            except jwt.PyJWTError as e:
                span.set_attribute('auth.result', 'invalid_jwt')
                logger.debug('Невалидный JWT: %s', e)
                return None

            if payload.get('type') != 'access':
                span.set_attribute('auth.result', 'wrong_type')
                return None

            jti = payload.get('jti')
            if not jti:
                span.set_attribute('auth.result', 'missing_jti')
                return None

            user_id = payload.get('sub')
            if not user_id:
                span.set_attribute('auth.result', 'missing_sub')
                return None

            # 2. Blacklist.
            if await self._is_blacklisted(jti):
                span.set_attribute('auth.result', 'blacklisted')
                logger.debug('Токен отозван')
                return None

            # 3. Token version.
            if not await self._version_ok(user_id, payload.get('ver', 1)):
                span.set_attribute('auth.result', 'version_stale')
                logger.debug('Токен устарел: user_ver изменена')
                return None

            span.set_attribute('auth.result', 'accepted')
            span.set_attribute('auth.user_id', user_id)
            return payload

    async def _is_blacklisted(self, jti: str) -> bool:
        """
        Проверяет blacklist в auth-redis.

        """
        if self.auth_redis is None:
            logger.warning('Auth-redis не инициализирован, blacklist fail-closed')
            return True

        try:
            return bool(await self.auth_redis.exists(f'{BLACKLIST_PREFIX}:{jti}'))
        except RedisError as e:
            logger.warning('Auth-redis недоступен при проверке blacklist, fail-closed: %s', e)
            return True

    async def _version_ok(self, user_id: str, token_ver: int | str) -> bool:
        """
        Проверяет, что версия токена не устарела.
        """
        if self.auth_redis is None:
            logger.warning('Auth-redis не инициализирован, user_ver fail-closed')
            return False

        try:
            raw = await self.auth_redis.get(f'{USER_VER_PREFIX}:{user_id}')
        except RedisError as e:
            logger.warning('Auth-redis недоступен при проверке user_ver, fail-closed: %s', e)
            return False

        if raw is None:
            return True

        try:
            current_ver = int(raw)
            payload_ver = int(token_ver)
        except (TypeError, ValueError):
            return False

        return payload_ver >= current_ver

    async def get_user_permissions(self, user_id: UUID) -> set[str]:
        """
        Возвращает множество прав пользователя.

        Источник истины:
          1. auth-redis: auth:perms:{user_id}
          2. HTTP fallback в auth-service
          3. пустое множество, если ничего не доступно

        """
        with tracer.start_as_current_span('TokenVerifier.get_user_permissions') as span:
            cache_key = f'{PERMS_CACHE_PREFIX}:{user_id}'

            # 1. Auth-redis.
            if self.auth_redis is not None:
                try:
                    cached = await self.auth_redis.get(cache_key)
                    if cached is not None:
                        try:
                            perms = set(json.loads(cached))
                            span.set_attribute('auth.perms_source', 'redis')
                            span.set_attribute('auth.perms_count', len(perms))
                            return perms
                        except (json.JSONDecodeError, TypeError):
                            logger.warning('Повреждённый кэш perms для %s', user_id)
                except RedisError as e:
                    logger.warning('Auth-redis недоступен для perms: %s', e)

            # 2. HTTP fallback.
            if self.auth_client is not None:
                perms = await self.auth_client.get_permissions(user_id)
                if perms is not None:
                    span.set_attribute('auth.perms_source', 'http')
                    span.set_attribute('auth.perms_count', len(perms))

                    # Write-back в auth-redis, если он доступен.
                    if self.auth_redis is not None:
                        try:
                            await self.auth_redis.set(
                                cache_key,
                                json.dumps(list(perms)),
                                ex=self.perms_ttl,
                            )
                        except RedisError as e:
                            logger.warning('Не удалось сохранить perms в auth-redis: %s', e)

                    return perms


            span.set_attribute('auth.perms_source', 'none')
            logger.warning('Не удалось определить права для %s, возвращаем пустое множество', user_id)
            return set()


@lru_cache(maxsize=1)
def get_auth_client() -> AuthClient:
    """Singleton AuthClient."""
    return AuthClient(base_url=config.AUTH_SERVICE_URL)