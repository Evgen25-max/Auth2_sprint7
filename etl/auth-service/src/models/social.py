from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuthorizeResponse(BaseModel):
    """Ответ эндпоинта /social/{provider}/authorize."""
    auth_url: str
    state: str


class SocialLoginRequest(BaseModel):
    """Тело запроса входа/привязки через соцсеть."""
    code: str = Field(..., description='Authorization code от провайдера')
    state: str = Field(..., description='State, полученный на /authorize')


class MergeAccountsRequest(BaseModel):
    """Тело запроса ручного объединения аккаунтов."""
    provider: str
    code: str
    state: str
    merge_password: str | None = Field(
        None,
        description='Пароль присоединяемого аккаунта, если у него задан пароль',
    )


class SocialAccountPublic(BaseModel):
    """Публичное представление привязанной соцсети."""
    provider: str
    external_id: str
    email: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    linked_at: datetime

    model_config = ConfigDict(from_attributes=True)