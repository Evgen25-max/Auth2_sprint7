
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from models.auth_models import Base
from dotenv import load_dotenv
from pathlib import Path

# Ищем .env в корне auth-service (на уровень выше alembic/)
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"[Alembic] Loaded .env from {env_path}")


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
AUTH_SCHEMA = os.getenv('POSTGRES_AUTH_SCHEMA', 'auth')


def get_url() -> str:
    """Собирает строку подключения из переменных окружения."""
    user = os.getenv('POSTGRES_AUTH_USER', 'auth_admin')
    password = os.getenv('POSTGRES_AUTH_PASSWORD', 'secret')
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    db = os.getenv('POSTGRES_AUTH_DB', 'auth_service_db')

    return f'postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}'


def include_name(name, type_, parent_names):
    """Фильтр: учитываем только объекты в схеме 'auth'."""
    if type_ == 'schema':
        return name in (AUTH_SCHEMA, None)
    if type_ == 'table':
        return parent_names.get('schema') == AUTH_SCHEMA
    return True


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        include_schemas=True,
        include_name=include_name,
        version_table_schema=AUTH_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=AUTH_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        {'sqlalchemy.url': get_url()},
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.execute(
            text(f'CREATE SCHEMA IF NOT EXISTS "{AUTH_SCHEMA}"')
        )
        await connection.commit()

        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()