
import json
import logging
from uuid import UUID

from api.const import PERMS_CACHE_PREFIX
from core.config import config
from db.postgres import get_session
from db.redis import get_redis
from db_work.abc_rbac import RBACRepository
from db_work.postgres_rbac import PostgresRBACRepository
from fastapi import Depends
from models.auth_models import Permission, Role
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from services.custom_exception import (PermissionNotFoundError,
                                       RoleAlreadyExistsError,
                                       RoleNotFoundError)
from services.exception_handler import handle_storage_errors

logger = logging.getLogger(__name__)


class RBACService:
    """Логика RBAC с Redis-кэша."""

    def __init__(
        self,
        repo: RBACRepository,
        redis: Redis,
        session: AsyncSession,
    ):
        self._repo = repo
        self._redis = redis
        self._session = session

    @handle_storage_errors
    async def create_role(
        self,
        name: str,
        description: str | None = None,
        permission_codenames: list[str] | None = None
    ) -> Role:
        """Создает роль и сразу назначает ей права."""
        if await self._repo.get_role_by_name(name):
            raise RoleAlreadyExistsError(name)

        perms_to_add = []
        if permission_codenames:
            for codename in permission_codenames:
                perm = await self._repo.get_permission_by_codename(codename)
                if perm is None:
                    raise PermissionNotFoundError(codename)
                perms_to_add.append(perm)

        role = await self._repo.create_role(
            name=name,
            description=description,
            permissions=perms_to_add
        )
        await self._session.commit()
        logger.info('Создана роль %s (id=%s) с правами: %s', role.name, role.id, [p.codename for p in perms_to_add])
        return role

    @handle_storage_errors
    async def delete_role(self, role_id: UUID) -> bool:
        """
        Удаляет роль и сбрасывает кэш прав у всех пользователей,
        которым она была назначена.
        """
        affected_user_ids = await self._repo.get_users_by_role_id(role_id)
        deleted = await self._repo.delete_role(role_id)
        if not deleted:
            raise RoleNotFoundError(str(role_id))
        await self._session.commit()
        for user_id in affected_user_ids:
            await self.invalidate_user_perms_cache(user_id)
        logger.info(
            'Удалена роль id=%s, сброшен кэш прав у %d пользователей',
            role_id,
            len(affected_user_ids),
        )
        return True

    @handle_storage_errors
    async def list_roles(self) -> list[Role]:
        return await self._repo.list_roles()

    @handle_storage_errors
    async def assign_role_to_user(self, user_id: UUID, role_name: str, commit: bool = True) -> None:
        role = await self._repo.get_role_by_name(role_name)
        if role is None:
            raise RoleNotFoundError(role_name)

        await self._repo.assign_role_to_user(user_id=user_id, role_id=role.id)
        await self.invalidate_user_perms_cache(user_id)
        logger.info('Пользователю %s назначена роль %s', user_id, role_name)

        if commit:
            await self._session.commit()

    @handle_storage_errors
    async def remove_role_from_user(self, user_id: UUID, role_name: str, commit: bool = True) -> None:
        role = await self._repo.get_role_by_name(role_name)
        if role is None:
            raise RoleNotFoundError(role_name)

        await self._repo.remove_role_from_user(user_id=user_id, role_id=role.id)
        await self.invalidate_user_perms_cache(user_id)
        logger.info('У пользователя %s отозвана роль %s', user_id, role_name)

        if commit:
            await self._session.commit()

    @handle_storage_errors
    async def add_permission_to_role(self, role_name: str, perm_codename: str) -> None:
        role = await self._repo.get_role_by_name(role_name)
        if role is None:
            raise RoleNotFoundError(role_name)

        perm = await self._repo.get_permission_by_codename(perm_codename)
        if perm is None:
            raise PermissionNotFoundError(perm_codename)

        await self._repo.add_permission_to_role(role_id=role.id, permission_id=perm.id)
        logger.info('К роли %s добавлено разрешение %s', role_name, perm_codename)


    @handle_storage_errors
    async def get_user_permissions(self, user_id: UUID) -> set[str]:
        """Возвращает множество codenames разрешений пользователя.

        Сначала проверяет Redis. Если нет — идет в Postgres и кэширует результат.
        """
        cache_key = f'{PERMS_CACHE_PREFIX}:{user_id}'
        try:
            cached_json = await self._redis.get(cache_key)
            if cached_json is not None:
                return set(json.loads(cached_json))
        except RedisError as e:
            logger.warning('Redis недоступен для чтения кэша разрешений: %s', e)

        perms_set = await self._repo.get_user_permissions(user_id)

        try:
            await self._redis.setex(
                cache_key,
                config.PERMS_CACHE_TTL_SECONDS,
                json.dumps(list(perms_set)),
            )
        except RedisError as e:
            logger.warning('Не удалось закэшировать права пользователя %s: %s', user_id, e)

        return perms_set

    @handle_storage_errors
    async def has_permission(self, user_id: UUID, codename: str) -> bool:
        """Быстрая проверка наличия одного конкретного права."""
        perms = await self.get_user_permissions(user_id)
        return codename in perms

    async def invalidate_user_perms_cache(self, user_id: UUID) -> None:
        """Сбрасывает кэш прав одного пользователя. Ошибки Redis логирует, но не роняет запрос."""
        cache_key = f'{PERMS_CACHE_PREFIX}:{user_id}'
        try:
            await self._redis.delete(cache_key)
        except RedisError as e:
            # Пункт 8: не падаем, кэш сам умрёт по TTL (максимум 15 минут)
            logger.warning('Не удалось очистить кэш прав для %s: %s', user_id, e)

    @handle_storage_errors
    async def get_role_by_name(self, name: str) -> Role | None:
        """Вспомогательный метод для получения роли по имени."""
        return await self._repo.get_role_by_name(name)


async def get_rbac_service(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> RBACService:
    """ Фабрика для RBACService."""
    repo = PostgresRBACRepository(session)
    return RBACService(repo=repo, redis=redis, session=session)
