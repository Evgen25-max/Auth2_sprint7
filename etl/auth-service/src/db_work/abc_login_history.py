
from abc import ABC, abstractmethod
from uuid import UUID

from models.auth_models import LoginHistory


class LoginHistoryRepository(ABC):
    """Интерфейс для записи и чтения истории аутентификации."""

    @abstractmethod
    async def record_login(
        self,
        user_id: UUID | None,
        login: str,
        ip_address: str | None,
        user_agent: str | None,
        success: bool,
    ) -> LoginHistory:
        """Записывает факт попытки входа."""
        ...

    @abstractmethod
    async def get_recent_logins(
        self, user_id: UUID, limit: int = 20
    ) -> list[LoginHistory]:
        """Возвращает последние N успешных/неуспешных входов пользователя."""
        ...
