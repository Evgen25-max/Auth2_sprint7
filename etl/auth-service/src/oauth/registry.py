from oauth.providers.yandex import YandexOAuthProvider
from services.custom_exception import OAuthProviderError

_REGISTRY: dict[str, 'object'] = {
    'yandex': YandexOAuthProvider(),
}


def get_provider(name: str):
    """Возвращает провайдер по имени. Бросает OAuthProviderError, если нет."""
    provider = _REGISTRY.get(name)
    if provider is None:
        raise OAuthProviderError(f'Неизвестный провайдер: {name}')
    return provider


def available_providers() -> list[str]:
    return list(_REGISTRY.keys())