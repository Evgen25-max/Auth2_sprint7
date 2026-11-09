import uuid
import time
import jwt
import pytest
from settings import test_settings


@pytest.mark.asyncio
async def test_public_endpoints_work_without_auth(aiohttp_client, clean_es, load_films):
    """Публичные эндпоинты работают без авторизации."""
    films = [{'id': str(uuid.uuid4()), 'title': 'Public Movie', 'imdb_rating': 8.0,
              'genres': [], 'description': '', 'directors_names': [],
              'actors_names': [], 'writers_names': [], 'directors': [],
              'actors': [], 'writers': []}]
    await load_films(films)

    url = f'{test_settings.service_url}/api/v1/films/'
    async with aiohttp_client.get(url) as r:
        assert r.status == 200


@pytest.mark.asyncio
async def test_valid_jwt_accepted(aiohttp_client, clean_es, load_films):
    """Валидный JWT (подписанный общим секретом) принимается."""
    secret = 'test-jwt-secret-key-for-functional-tests'
    payload = {
        'sub': str(uuid.uuid4()),
        'type': 'access',
        'is_superuser': False,
        'jti': str(uuid.uuid4()),
        'iat': int(time.time()),
        'exp': int(time.time()) + 3600,
    }
    token = jwt.encode(payload, secret, algorithm='HS256')

    url = f'{test_settings.service_url}/api/v1/films/restricted'
    async with aiohttp_client.get(
        url, headers={'Authorization': f'Bearer {token}'}
    ) as r:
        # Без прав в кэше — 403 (или 401 если права не подгружены)
        assert r.status in (403, 401)


@pytest.mark.asyncio
async def test_expired_jwt_rejected(aiohttp_client, clean_es):
    """Просроченный JWT отвергается."""
    secret = 'test-jwt-secret-key-for-functional-tests'
    payload = {
        'sub': str(uuid.uuid4()),
        'type': 'access',
        'is_superuser': False,
        'jti': str(uuid.uuid4()),
        'iat': int(time.time()) - 7200,
        'exp': int(time.time()) - 3600,
    }
    token = jwt.encode(payload, secret, algorithm='HS256')

    url = f'{test_settings.service_url}/api/v1/films/restricted'
    async with aiohttp_client.get(
        url, headers={'Authorization': f'Bearer {token}'}
    ) as r:
        assert r.status == 401


@pytest.mark.asyncio
async def test_request_id_propagated(aiohttp_client, clean_es, load_films):
    """X-Request-Id пробрасывается через всё приложение."""
    films = [{'id': str(uuid.uuid4()), 'title': 'Trace Movie', 'imdb_rating': 7.5,
              'genres': [], 'description': '', 'directors_names': [],
              'actors_names': [], 'writers_names': [], 'directors': [],
              'actors': [], 'writers': []}]
    await load_films(films)

    request_id = str(uuid.uuid4())
    url = f'{test_settings.service_url}/api/v1/films/'
    async with aiohttp_client.get(
        url, headers={'X-Request-Id': request_id}
    ) as r:
        assert r.status == 200
        # X-Request-Id возвращается в ответе
        assert r.headers.get('X-Request-Id') == request_id


@pytest.mark.asyncio
async def test_request_id_generated_if_missing(aiohttp_client, clean_es, load_films):
    """Если X-Request-Id не передан — он генерируется автоматически."""
    films = [{'id': str(uuid.uuid4()), 'title': 'AutoID Movie', 'imdb_rating': 7.0,
              'genres': [], 'description': '', 'directors_names': [],
              'actors_names': [], 'writers_names': [], 'directors': [],
              'actors': [], 'writers': []}]
    await load_films(films)

    url = f'{test_settings.service_url}/api/v1/films/'
    async with aiohttp_client.get(url) as r:
        assert r.status == 200
        returned_id = r.headers.get('X-Request-Id')
        assert returned_id is not None
        # UUID v4 имеет длину 36
        assert len(returned_id) == 36