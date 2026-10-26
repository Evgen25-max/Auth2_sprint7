
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from models.auth_models import User


class UserRepository(ABC):
    """Интерфейс для работы с User."""

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Получает пользователя по ID."""
        ...

    @abstractmethod
    async def get_by_login(self, login: str) -> Optional[User]:
        """Получает пользователя по логину (для входа/регистрации)."""
        ...

    @abstractmethod
    async def create(
        self,
        login: str,
        hashed_password: str,
        first_name: str,
        last_name: str,
        is_superuser: bool = False,
    ) -> User:
        """Создает нового пользователя."""
        ...

    @abstractmethod
    async def update_password(self, user_id: UUID, new_hashed_password: str) -> None:
        """Обновляет пароль пользователя."""
        ...

    @abstractmethod
    async def update_profile(
        self,
        user_id: UUID,
        login: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        """Обновляет профильные данные (без пароля)."""
        ...
