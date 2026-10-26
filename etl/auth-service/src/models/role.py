from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoleCreate(BaseModel):
    """Создание роли."""

    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RolePublic(BaseModel):
    """Роль с правами."""

    id: UUID
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator('permissions', mode='before')
    @classmethod
    def extract_permission_codenames(cls, v):
        """
        list[Permission] -> list[str] codename'ов.
        """
        if not v:
            return []
        if hasattr(v[0], 'codename'):
            return [perm.codename for perm in v]
        return v
