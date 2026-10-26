
from core.config import config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import DeclarativeBase

engine = create_async_engine(
    config.database_url,
    echo=config.POSTGRES_ECHO,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=5,
    pool_recycle=1800,
)

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Базовый класс моделей."""


async def get_session() -> AsyncSession:
    """Dependency: одна сессия на запрос."""
    async with async_session() as session:
        yield session


async def check_postgres() -> None:
    """Проверка доступности БД при старте."""
    async with engine.connect() as conn:
        await conn.execute(text('SELECT 1'))


async def close_postgres() -> None:
    """Освобождает пул соединений."""
    await engine.dispose()
