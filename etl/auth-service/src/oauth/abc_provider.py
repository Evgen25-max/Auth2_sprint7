from abc import ABC, abstractmethod

from oauth.schemas import SocialUserInfo


class OAuthProvider(ABC):
    """
    Абстракция OAuth-провайдера.
    """

    name: str = ''

    @abstractmethod
    def get_auth_url(self, state: str, redirect_uri: str | None = None) -> str:
        """Собирает URL для редиректа пользователя на страницу авторизации."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str) -> dict:
        """Обменивает authorization_code на access_token провайдера."""
        ...

    @abstractmethod
    async def fetch_user_info(self, access_token: str) -> SocialUserInfo:
        """Запрашивает профиль пользователя у провайдера и нормализует его."""
        ...