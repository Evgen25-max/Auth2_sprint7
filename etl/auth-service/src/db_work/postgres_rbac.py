from typing import Optional
from uuid import UUID

from models.auth_models import Permission, Role, RolePermission, UserRole
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db_work.abc_rbac import RBACRepository


class PostgresRBACRepository(RBACRepository):
    """Работа с таблицами auth.roles, auth.permissions, auth.user_roles, auth.role_permissions."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # --- Роли ---

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        stmt = select(Role).where(Role.name == name)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def create_role(
        self,
        name: str,
        description: str | None,
        permissions: list[Permission] | None = None,
    ) -> Role:
        role = Role(name=name, description=description)
        if permissions:
            role.permissions.extend(permissions)

        self._session.add(role)
        await self._session.flush()
        return role

    async def delete_role(self, role_id: UUID) -> bool:
        """Удаляет роль. НЕ делает commit — это ответственность сервиса."""
        role = await self._session.get(Role, role_id)
        if role is None:
            return False

        await self._session.delete(role)
        await self._session.flush()
        return True

    async def list_roles(self) -> list[Role]:
        stmt = select(Role).options(joinedload(Role.permissions))
        result = await self._session.execute(stmt)
        return list(result.unique().scalars().all())

    # === НОВЫЙ МЕТОД: список пользователей, у которых была эта роль ===
    async def get_users_by_role_id(self, role_id: UUID) -> list[UUID]:
        """Возвращает user_id всех пользователей, имеющих указанную роль."""
        stmt = select(UserRole.user_id).where(UserRole.role_id == role_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # --- Назначение ролей ---

    async def assign_role_to_user(self, user_id: UUID, role_id: UUID) -> None:
        stmt = select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
        existing = await self._session.execute(stmt)
        if existing.scalars().first():
            return

        link = UserRole(user_id=user_id, role_id=role_id)
        self._session.add(link)
        await self._session.flush()

    async def remove_role_from_user(self, user_id: UUID, role_id: UUID) -> None:
        stmt = delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_user_roles(self, user_id: UUID) -> list[Role]:
        stmt = (
            select(Role)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # --- Разрешения ---

    async def get_permission_by_codename(self, codename: str) -> Optional[Permission]:
        stmt = select(Permission).where(Permission.codename == codename)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def add_permission_to_role(self, role_id: UUID, permission_id: UUID) -> None:
        stmt = select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
        existing = await self._session.execute(stmt)
        if existing.scalars().first():
            return

        link = RolePermission(role_id=role_id, permission_id=permission_id)
        self._session.add(link)
        await self._session.flush()

    async def remove_permission_from_role(self, role_id: UUID, permission_id: UUID) -> None:
        stmt = delete(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_user_permissions(self, user_id: UUID) -> set[str]:
        stmt = (
            select(Permission.codename)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.id)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())