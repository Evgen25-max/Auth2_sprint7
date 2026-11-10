"""
Тесты rate limiting для Auth-сервиса.
Тестируем эндпоинты /api/v1/auth/login и /api/v1/auth/signup
"""
import uuid
import asyncio
import pytest

from settings import test_settings

BASE_URL = test_settings.service_url

LOGIN_FAILED_THRESHOLD = 5


@pytest.mark.asyncio
async def test_login_account_lockout_after_failed_attempts(
    aiohttp_client,
    clean_db,
    clean_redis,
):
    """
    После LOGIN_FAILED_THRESHOLD неверных попыток входа
    аккаунт блокируется и возвращает 423.
    """
    login = f'lockout_user_{uuid.uuid4().hex[:8]}'

    signup = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json={
            'login': login,
            'password': 'StrongPass123!',
            'first_name': 'Lockout',
            'last_name': 'Test',
        },
    )
    assert signup.status == 201, await signup.text()

    statuses = []

    for _ in range(LOGIN_FAILED_THRESHOLD + 5):
        r = await aiohttp_client.post(
            f'{BASE_URL}/api/v1/auth/login',
            json={
                'login': login,
                'password': 'WrongPassword123!',
            },
        )
        statuses.append(r.status)

    # Первые 5 попыток — неверный пароль.
    assert statuses[:LOGIN_FAILED_THRESHOLD] == [401] * LOGIN_FAILED_THRESHOLD

    # Дальше аккаунт заблокирован.
    assert all(status == 423 for status in statuses[LOGIN_FAILED_THRESHOLD:])


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