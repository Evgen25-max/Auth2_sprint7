from dataclasses import dataclass, field


@dataclass
class SocialUserInfo:
    """Нормализованный профиль пользователя, полученный от OAuth-провайдера."""
    external_id: str
    provider: str
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    raw: dict = field(default_factory=dict)