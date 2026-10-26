
from pydantic import BaseModel


class TokenPair(BaseModel):
    """Пара токенов."""

    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class RefreshRequest(BaseModel):
    """Тело запроса обновления access-токена."""

    refresh_token: str


class CheckAccessRequest(BaseModel):
    """Тело запроса проверки права."""

    permission: str
