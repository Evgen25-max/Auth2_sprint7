"""
Шаблон провайдера для ВК.

Чтобы подключить ВК:
  1. Реализовать методы ниже, используя актуальный ВК API:
       - Авторизация:  https://id.vk.com/authorize
       - Токен:        POST https://id.vk.com/oauth2/auth
       - Профиль:      POST https://id.vk.com/oauth2/user_info
       (ВК использует PKCE, поэтому потребуется генерировать
        code_verifier / code_challenge и сохранять их в state.)
  2. Заполнить в .env: VK_CLIENT_ID, VK_CLIENT_SECRET, VK_REDIRECT_URI.
  3. Зарегистрировать экземпляр в oauth/registry.py:
       _REGISTRY['vk'] = VKOAuthProvider()
"""
from oauth.abc_provider import OAuthProvider
from oauth.schemas import SocialUserInfo


class VKOAuthProvider(OAuthProvider):
    name = 'vk'

    def get_auth_url(self, state: str, redirect_uri: str | None = None) -> str:
        raise NotImplementedError('VK-провайдер ещё не реализован')

    async def exchange_code(self, code: str) -> dict:
        raise NotImplementedError('VK-провайдер ещё не реализован')

    async def fetch_user_info(self, access_token: str) -> SocialUserInfo:
        raise NotImplementedError('VK-провайдер ещё не реализован')