from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from models.auth_models import User


class UserRepository(ABC):
    """Интерфейс для работы с User."""

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        ...

    @abstractmethod
    async def get_by_login(self, login: str) -> Optional[User]:
        ...

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Получает пользователя по доверенному email (для OAuth-связывания)."""
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
        ...

    @abstractmethod
    async def create_oauth_user(
        self,
        login: str,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        """Создаёт пользователя без пароля (для входа через соцсеть). НЕ делает commit."""
        ...

    @abstractmethod
    async def update_password(self, user_id: UUID, new_hashed_password: str) -> None:
        ...

    @abstractmethod
    async def update_profile(
        self,
        user_id: UUID,
        login: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        ...

    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        """Удаляет пользователя. НЕ делает commit."""
        ...