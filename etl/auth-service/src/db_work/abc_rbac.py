
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from models.auth_models import Permission, Role


class RBACRepository(ABC):
    """Интерфейс для управления ролями и правами."""

    # --- Роли ---

    @abstractmethod
    async def get_role_by_name(self, name: str) -> Optional[Role]:
        """Ищет роль по имени."""
        ...

    @abstractmethod
    async def create_role(self, name: str, description: str | None = None) -> Role:
        """Создает новую роль."""
        ...

    @abstractmethod
    async def delete_role(self, role_id: UUID) -> bool:
        """Удаляет роль. Возвращает True, если удалена, False, если не найдена."""
        ...

    @abstractmethod
    async def list_roles(self) -> list[Role]:
        """Возвращает список всех ролей."""
        ...

    # --- Назначение ролей пользователю ---

    @abstractmethod
    async def assign_role_to_user(self, user_id: UUID, role_id: UUID) -> None:
        """Назначает роль пользователю (M2M)."""
        ...

    @abstractmethod
    async def remove_role_from_user(self, user_id: UUID, role_id: UUID) -> None:
        """Отозывает роль у пользователя."""
        ...

    @abstractmethod
    async def get_user_roles(self, user_id: UUID) -> list[Role]:
        """Получает список ролей пользователя."""
        ...

    # --- Разрешения ---

    @abstractmethod
    async def get_permission_by_codename(self, codename: str) -> Optional[Permission]:
        """Ищет разрешение по кодовому имени."""
        ...

    @abstractmethod
    async def add_permission_to_role(self, role_id: UUID, permission_id: UUID) -> None:
        """Добавляет разрешение в роль."""
        ...

    @abstractmethod
    async def remove_permission_from_role(self, role_id: UUID, permission_id: UUID) -> None:
        """Убирает разрешение из роли."""
        ...

    @abstractmethod
    async def get_user_permissions(self, user_id: UUID) -> set[str]:
        """
        Получает множество кодовых имен разрешений (codenames) для пользователя.
        Учитывает все его роли.
        """
        ...
