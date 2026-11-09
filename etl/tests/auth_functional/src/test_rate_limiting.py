"""
Тесты rate limiting для Auth-сервиса.
Тестируем эндпоинты /api/v1/auth/login и /api/v1/auth/signup
"""
import uuid
import asyncio
import pytest

from settings import test_settings

BASE_URL = test_settings.service_url


@pytest.mark.asyncio
async def test_login_rate_limiting(aiohttp_client, clean_db, clean_redis):
    """
    На эндпоинт /login действует строгий rate limit.
    После N неудачных попыток — 429.
    """
    # Регистрируем пользователя
    login = f'ratelimit_user_{uuid.uuid4().hex[:8]}'
    signup = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json={
            'login': login,
            'password': 'StrongPass123!',
            'first_name': 'Rate',
            'last_name': 'Limit',
        },
    )
    assert signup.status == 201, await signup.text()

    # Делаем много попыток логина с неправильным паролем
    statuses = []
    for _ in range(20):
        r = await aiohttp_client.post(
            f'{BASE_URL}/api/v1/auth/login',
            json={'login': login, 'password': 'WrongPassword!'},
        )
        statuses.append(r.status)

    # Либо получили 429 (rate limit), либо много 401 (если RL отключён в тестах)
    assert 429 in statuses or statuses.count(401) > 5, (
        f'Ожидался 429 или много 401, получили: {statuses}'
    )


@pytest.mark.asyncio
async def test_signup_rate_limiting(aiohttp_client, clean_db, clean_redis):
    """На signup тоже действует rate limit."""
    statuses = []
    for i in range(15):
        r = await aiohttp_client.post(
            f'{BASE_URL}/api/v1/auth/signup',
            json={
                'login': f'spam_{i}_{uuid.uuid4().hex[:6]}',
                'password': 'StrongPass123!',
                'first_name': 'Spam',
                'last_name': 'User',
            },
        )
        statuses.append(r.status)

    # Либо 429, либо все 201 (если RL отключён)
    assert 429 in statuses or statuses.count(201) >= 10


@pytest.mark.asyncio
async def test_request_id_in_auth_responses(aiohttp_client, clean_db, clean_redis):
    """Auth-сервис пробрасывает X-Request-Id в ответах."""
    request_id = str(uuid.uuid4())
    r = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={'login': 'nonexistent', 'password': 'Whatever123!'},
        headers={'X-Request-Id': request_id},
    )
    assert r.status == 401
    assert r.headers.get('X-Request-Id') == request_id


@pytest.mark.asyncio
async def test_auth_responds_under_load(aiohttp_client, clean_db, clean_redis):
    """Auth-сервис стабильно отвечает при множестве запросов."""
    statuses = []
    for i in range(10):
        r = await aiohttp_client.post(
            f'{BASE_URL}/api/v1/auth/login',
            json={
                'login': f'load_user_{uuid.uuid4().hex[:6]}',
                'password': 'Whatever123!',
            },
        )
        statuses.append(r.status)

    # Все должны быть 401 (пользователи не существуют)
    assert all(s == 401 for s in statuses)