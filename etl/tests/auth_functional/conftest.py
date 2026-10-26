import uuid
import hashlib
import aiohttp
import asyncio
import asyncpg
import pytest_asyncio
import redis.asyncio as redis
from passlib.context import CryptContext

from settings import test_settings

BASE_URL = test_settings.service_url

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

SYSTEM_PERMISSIONS = [
    ('user.manage', 'Управление пользователями'),
    ('role.manage', 'Управление ролями и правами'),
    ('film.restricted.view', 'Просмотр фильмов с ограниченным доступом'),
]

SYSTEM_ROLES = [
    ('user', 'Базовый пользователь', []),
    (
        'admin',
        'Администратор сервиса',
        [
            'user.manage',
            'role.manage',
            'film.restricted.view',
        ],
    ),
]

async def hash_password(password: str) -> str:
    """
    Асинхронно хеширует пароль так же, как это делает auth-service.
    Обязательно используем тот же PASSWORD_PEPPER и SHA-256.
    """
    password_with_pepper = f'{password}{test_settings.password_pepper}'
    sha256_hash = hashlib.sha256(password_with_pepper.encode('utf-8')).hexdigest()
    return await asyncio.to_thread(pwd_context.hash, sha256_hash)


async def reset_auth_db(conn: asyncpg.Connection) -> None:
    """
    Полностью очищает схему auth и заново сеет системные права/роли.
    """
    schema = test_settings.auth_schema

    await conn.execute(f"""
        TRUNCATE TABLE
            {schema}.login_history,
            {schema}.user_roles,
            {schema}.role_permissions,
            {schema}.users,
            {schema}.roles,
            {schema}.permissions
        RESTART IDENTITY CASCADE
    """)

    perm_ids: dict[str, str] = {}

    for codename, name in SYSTEM_PERMISSIONS:
        row = await conn.fetchrow(f"""
            INSERT INTO {schema}.permissions (codename, name)
            VALUES ($1, $2)
            ON CONFLICT (codename)
            DO UPDATE SET name = EXCLUDED.name
            RETURNING id, codename
        """, codename, name)

        perm_ids[row['codename']] = row['id']

    for role_name, description, codenames in SYSTEM_ROLES:
        role_row = await conn.fetchrow(f"""
            INSERT INTO {schema}.roles (name, description)
            VALUES ($1, $2)
            ON CONFLICT (name)
            DO UPDATE SET description = EXCLUDED.description
            RETURNING id
        """, role_name, description)

        role_id = role_row['id']

        await conn.execute(f"""
            DELETE FROM {schema}.role_permissions
            WHERE role_id = $1
        """, role_id)

        for codename in codenames:
            await conn.execute(f"""
                INSERT INTO {schema}.role_permissions (role_id, permission_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
            """, role_id, perm_ids[codename])


@pytest_asyncio.fixture(scope='function')
async def aiohttp_client():
    """HTTP-клиент для запросов к auth-service."""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest_asyncio.fixture(scope='function')
async def db_conn():
    """Соединение с PostgreSQL для cleanup/seed."""
    conn = await asyncpg.connect(
        host=test_settings.postgres_host,
        port=test_settings.postgres_port,
        user=test_settings.postgres_user,
        password=test_settings.postgres_password,
        database=test_settings.postgres_db,
    )

    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope='function')
async def clean_db(db_conn: asyncpg.Connection):
    """
    Очищает БД перед каждым тестом и восстанавливает системные роли/права.
    """
    await reset_auth_db(db_conn)
    yield db_conn


@pytest_asyncio.fixture(scope='function')
async def clean_redis():
    """
    Очищает Redis DB, где auth-service хранит:
    - blacklist
    - active refresh
    - perms cache
    - version, если добавишь logout-all
    """
    client = redis.Redis(
        host=test_settings.redis_host,
        port=test_settings.redis_port,
        password=test_settings.redis_password,
        db=test_settings.redis_db,
        decode_responses=True,
    )

    await client.flushdb()

    yield client

    await client.aclose()


@pytest_asyncio.fixture(scope='function')
async def admin_token(
    clean_db: asyncpg.Connection,
    clean_redis: redis.Redis,
    aiohttp_client: aiohttp.ClientSession,
):
    """
    Создает суперпользователя напрямую в БД и возвращает его access_token.
    """
    schema = test_settings.auth_schema
    login = 'admin'
    password = 'AdminPass123!'

    hashed = await hash_password(password)

    await clean_db.execute(f"""
        INSERT INTO {schema}.users (
            login,
            hashed_password,
            first_name,
            last_name,
            is_superuser
        )
        VALUES ($1, $2, $3, $4, true)
        ON CONFLICT (login)
        DO UPDATE SET
            hashed_password = EXCLUDED.hashed_password,
            is_superuser = true
    """, login, hashed, 'Super', 'Admin')

    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': login,
            'password': password,
        },
    )

    assert response.status == 200, await response.text()

    data = await response.json()
    return data['access_token']


@pytest_asyncio.fixture(scope='function')
async def registered_user(
    clean_db: asyncpg.Connection,
    clean_redis: redis.Redis,
    aiohttp_client: aiohttp.ClientSession,
):
    """
    Регистрирует обычного пользователя через API и возвращает:
    - данные пользователя
    - access_token
    - refresh_token
    """
    login = f'user_{uuid.uuid4().hex[:10]}'
    password = 'UserPass123!'

    signup_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json={
            'login': login,
            'password': password,
            'first_name': 'Test',
            'last_name': 'User',
        },
    )

    assert signup_response.status == 201, await signup_response.text()
    user = await signup_response.json()

    login_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': login,
            'password': password,
        },
    )

    assert login_response.status == 200, await login_response.text()
    tokens = await login_response.json()

    return {
        'user': user,
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'password': password,
    }
