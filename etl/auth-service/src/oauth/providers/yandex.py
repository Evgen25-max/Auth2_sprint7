from urllib.parse import urlencode

import httpx

from core.config import config
from oauth.abc_provider import OAuthProvider
from oauth.schemas import SocialUserInfo
from services.custom_exception import OAuthProviderError


class YandexOAuthProvider(OAuthProvider):
    """OAuth-провайдер для Yandex ID."""

    name = 'yandex'
    SCOPE = 'login:info login:email login:avatar'

    def get_auth_url(self, state: str, redirect_uri: str | None = None) -> str:
        redirect_uri = redirect_uri or config.YANDEX_REDIRECT_URI
        params = {
            'response_type': 'code',
            'client_id': config.YANDEX_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'scope': self.SCOPE,
            'state': state,
        }
        return f'{config.YANDEX_AUTH_URL}?{urlencode(params)}'

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.YANDEX_TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': config.YANDEX_CLIENT_ID,
                    'client_secret': config.YANDEX_CLIENT_SECRET,
                },
            )
        if response.status_code != 200:
            raise OAuthProviderError(
                f'Yandex: не удалось обменять code на токен '
                f'(status={response.status_code})'
            )
        data = response.json()
        if 'access_token' not in data:
            raise OAuthProviderError('Yandex: в ответе нет access_token')
        return data

    async def fetch_user_info(self, access_token: str) -> SocialUserInfo:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                config.YANDEX_INFO_URL,
                params={'format': 'json'},
                headers={'Authorization': f'OAuth {access_token}'},
            )
        if response.status_code != 200:
            raise OAuthProviderError(
                f'Yandex: не удалось получить профиль '
                f'(status={response.status_code})'
            )
        data = response.json()

        avatar_url = None
        if data.get('default_avatar_id'):
            avatar_url = (
                f"https://avatars.yandex.net/get-yapic/"
                f"{data['default_avatar_id']}/islands-200"
            )

        return SocialUserInfo(
            external_id=str(data['id']),
            provider=self.name,
            email=data.get('default_email'),
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            username=data.get('login'),
            avatar_url=avatar_url,
            raw=data,
        )