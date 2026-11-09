from typing import Optional
from uuid import UUID

from models.auth_models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db_work.abc_users import UserRepository
from core.tracing_decorators import trace_class


@trace_class
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

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == email)
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

    async def create_oauth_user(
        self,
        login: str,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        """Создаёт пользователя без пароля. НЕ делает commit."""
        user = User(
            login=login,
            hashed_password=None,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_superuser=False,
        )
        self._session.add(user)
        await self._session.flush()
        return user

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

    async def delete(self, user_id: UUID) -> None:
        """Удаляет пользователя. НЕ делает commit."""
        user = await self._session.get(User, user_id)
        if user is not None:
            await self._session.delete(user)
            await self._session.flush()