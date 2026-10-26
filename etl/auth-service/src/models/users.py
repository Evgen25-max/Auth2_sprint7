from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    """Регистрация."""

    login: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=256)
    first_name: str = Field(..., max_length=50)
    last_name: str = Field(..., max_length=50)


class UserLogin(BaseModel):
    """Вход."""

    login: str
    password: str


class UserUpdate(BaseModel):
    current_password: str | None = None
    login: str | None = Field(None, min_length=3, max_length=255)
    password: str | None = Field(None, min_length=8, max_length=256)
    first_name: str | None = Field(None, max_length=50)
    last_name: str | None = Field(None, max_length=50)


class UserPublic(BaseModel):
    """Ответ наружу: без hashed_password."""

    id: UUID
    login: str
    first_name: str | None = None
    last_name: str | None = None
    roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator('roles', mode='before')
    @classmethod
    def extract_role_names(cls, v):
        """Извлекает имена ролей из объектов Role ORM."""
        if not v:
            return []
        if v and hasattr(v[0], 'name'):
            return [role.name for role in v]
        return v
