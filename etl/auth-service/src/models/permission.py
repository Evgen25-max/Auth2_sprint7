
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PermissionPublic(BaseModel):
    """Справочник разрешений."""

    id: UUID
    codename: str
    name: str

    model_config = ConfigDict(from_attributes=True)
