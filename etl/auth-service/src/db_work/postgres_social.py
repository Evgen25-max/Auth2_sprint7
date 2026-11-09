from uuid import UUID

from models.auth_models import LoginHistory, UserSocialAccount
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db_work.abc_social import SocialAccountRepository
from core.tracing_decorators import trace_class


@trace_class
class PostgresSocialAccountRepository(SocialAccountRepository):
    """Работа с таблицей auth.user_social_accounts."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_link(self, provider: str, external_id: str) -> UserSocialAccount | None:
        stmt = select(UserSocialAccount).where(
            UserSocialAccount.provider == provider,
            UserSocialAccount.external_id == external_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_link_for_user(self, user_id: UUID, provider: str) -> UserSocialAccount | None:
        stmt = select(UserSocialAccount).where(
            UserSocialAccount.user_id == user_id,
            UserSocialAccount.provider == provider,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_links_by_user(self, user_id: UUID) -> list[UserSocialAccount]:
        stmt = select(UserSocialAccount).where(UserSocialAccount.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_links(self, user_id: UUID, exclude_provider: str | None = None) -> int:
        stmt = select(func.count()).select_from(UserSocialAccount).where(
            UserSocialAccount.user_id == user_id
        )
        if exclude_provider is not None:
            stmt = stmt.where(UserSocialAccount.provider != exclude_provider)
        result = await self._session.execute(stmt)
        return int(result.scalar() or 0)

    async def create_link(
        self,
        user_id: UUID,
        provider: str,
        external_id: str,
        email: str | None = None,
        phone: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        raw_data: dict | None = None,
    ) -> UserSocialAccount:
        link = UserSocialAccount(
            user_id=user_id,
            provider=provider,
            external_id=external_id,
            email=email,
            phone=phone,
            username=username,
            avatar_url=avatar_url,
            raw_data=raw_data,
        )
        self._session.add(link)
        await self._session.flush()
        return link

    async def delete_link(self, user_id: UUID, provider: str) -> bool:
        link = await self.get_link_for_user(user_id, provider)
        if link is None:
            return False
        await self._session.delete(link)
        await self._session.flush()
        return True

    async def reassign_links(self, from_user_id: UUID, to_user_id: UUID) -> None:
        """
        Переносит привязки с одного юзера на другого.
        Если у целевого юзера уже есть привязка того же провайдера —
        привязка источника удаляется (конфликт).
        НЕ делает commit.
        """
        source_links = await self.get_links_by_user(from_user_id)
        for link in source_links:
            existing_target = await self.get_link_for_user(to_user_id, link.provider)
            if existing_target is not None:
                await self._session.delete(link)
            else:
                link.user_id = to_user_id
        await self._session.flush()

    async def reassign_login_history(self, from_user_id: UUID, to_user_id: UUID) -> None:
        """Переносит историю входов. НЕ делает commit."""
        stmt = (
            update(LoginHistory)
            .where(LoginHistory.user_id == from_user_id)
            .values(user_id=to_user_id)
        )
        await self._session.execute(stmt)