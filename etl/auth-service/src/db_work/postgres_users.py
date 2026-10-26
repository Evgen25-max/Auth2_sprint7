from typing import Optional
from uuid import UUID

from models.auth_models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db_work.abc_users import UserRepository


class PostgresUserRepository(UserRepository):
    """Работа с таблицей auth.users."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_login(self, login: str) -> Optional[User]:
        stmt = (
            select(User)
            .options(selectinload(User.roles)) 
            .where(User.login == login)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def create(
        self,
        login: str,
        hashed_password: str,
        first_name: str,
        last_name: str,
        is_superuser: bool = False,
    ) -> User:
        user = User(
            login=login,
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            is_superuser=is_superuser,
        )
        self._session.add(user)
        await self._session.commit()

        fresh_user = await self.get_by_id(user.id)
        if fresh_user is None:
             raise ValueError("User created but not found immediately after commit")

        return fresh_user

    async def update_password(self, user_id: UUID, new_hashed_password: str) -> None:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")

        user.hashed_password = new_hashed_password
        await self._session.commit()

    async def update_profile(
        self,
        user_id: UUID,
        login: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")

        if login is not None:
            user.login = login
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name

        await self._session.commit()

        return await self.get_by_id(user_id)