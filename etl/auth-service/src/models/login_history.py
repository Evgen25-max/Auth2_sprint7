
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LoginHistoryItem(BaseModel):
    """Запись истории."""

    id: UUID
    login: str
    ip_address: str | None = None
    user_agent: str | None = None
    success: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
