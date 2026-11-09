from abc import ABC, abstractmethod
from uuid import UUID

from models.auth_models import UserSocialAccount


class SocialAccountRepository(ABC):
    """Интерфейс для работы с привязками соцсетей."""

    @abstractmethod
    async def get_link(self, provider: str, external_id: str) -> UserSocialAccount | None:
        """Ищет привязку по провайдеру и внешнему ID."""
        ...

    @abstractmethod
    async def get_link_for_user(self, user_id: UUID, provider: str) -> UserSocialAccount | None:
        """Ищет привязку конкретного пользователя к конкретному провайдеру."""
        ...

    @abstractmethod
    async def get_links_by_user(self, user_id: UUID) -> list[UserSocialAccount]:
        """Все привязки пользователя."""
        ...

    @abstractmethod
    async def count_links(self, user_id: UUID, exclude_provider: str | None = None) -> int:
        """Количество привязок пользователя (опц. исключая провайдер)."""
        ...

    @abstractmethod
    async def create_link(
        self,
        user_id: UUID,
        provider: str,
        external_id: str,
        email: str | None = None,
        phone: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        raw_data: dict | None = None,
    ) -> UserSocialAccount:
        """Создаёт привязку. НЕ делает commit."""
        ...

    @abstractmethod
    async def delete_link(self, user_id: UUID, provider: str) -> bool:
        """Удаляет привязку. НЕ делает commit."""
        ...

    @abstractmethod
    async def reassign_links(self, from_user_id: UUID, to_user_id: UUID) -> None:
        """Переносит привязки одного пользователя другому (для объединения)."""
        ...

    @abstractmethod
    async def reassign_login_history(self, from_user_id: UUID, to_user_id: UUID) -> None:
        """Переносит историю входов одного пользователя другому."""
        ...