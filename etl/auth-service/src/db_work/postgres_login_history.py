
from uuid import UUID

from models.auth_models import LoginHistory
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db_work.abc_login_history import LoginHistoryRepository


class PostgresLoginHistoryRepository(LoginHistoryRepository):
    """Работа с таблицей auth.login_history."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def record_login(
        self,
        user_id: UUID | None,
        login: str,
        ip_address: str | None,
        user_agent: str | None,
        success: bool,
    ) -> LoginHistory:
        entry = LoginHistory(
            user_id=user_id,
            login=login,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
        )
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def get_recent_logins(
        self, user_id: UUID, limit: int = 20
    ) -> list[LoginHistory]:
        stmt = (
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(desc(LoginHistory.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
