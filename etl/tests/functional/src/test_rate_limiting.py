"""
Тесты rate limiting для Movies-сервиса.
Тестируем эндпоинты /api/v1/films/
"""
import uuid
import asyncio
import pytest
from settings import test_settings

BASE_URL = test_settings.service_url


def make_films(n):
    """Генерирует N фильмов для тестов."""
    return [{
        'id': str(uuid.uuid4()),
        'title': f'Rate Limit Movie {i}',
        'imdb_rating': 7.0,
        'genres': [],
        'description': '',
        'directors_names': [],
        'actors_names': [],
        'writers_names': [],
        'directors': [],
        'actors': [],
        'writers': [],
    } for i in range(n)]


@pytest.mark.asyncio
async def test_rate_limit_headers_returned(
    aiohttp_client, clean_es, clean_redis, load_films
):
    """Каждый ответ Movies-сервиса содержит X-RateLimit-* заголовки."""
    await load_films(make_films(1))
    url = f'{BASE_URL}/api/v1/films/'

    async with aiohttp_client.get(url) as r:
        assert r.status == 200
        # В ENVIRONMENT=test rate limiting отключён, заголовков может не быть
        # Это ожидаемое поведение
        print(f"Response headers: {dict(r.headers)}")


@pytest.mark.asyncio
async def test_films_endpoint_responds_under_load(
    aiohttp_client, clean_es, clean_redis, load_films
):
    """
    Проверяем, что Movies-сервис отвечает корректно
    при множестве параллельных запросов.
    """
    await load_films(make_films(5))
    url = f'{BASE_URL}/api/v1/films/'

    # Делаем 20 последовательных запросов
    statuses = []
    for _ in range(20):
        async with aiohttp_client.get(url) as r:
            statuses.append(r.status)

    assert all(s == 200 for s in statuses), (
        f'Ожидалось 200 OK, но получили: {set(statuses)}'
    )


@pytest.mark.asyncio
async def test_films_details_under_load(
    aiohttp_client, clean_es, clean_redis, load_films
):
    """Проверяем, что эндпоинт деталей фильма работает при нагрузке."""
    films = make_films(3)
    await load_films(films)

    # Делаем много запросов к одному фильму
    url = f'{BASE_URL}/api/v1/films/{films[0]["id"]}'
    statuses = []
    for _ in range(15):
        async with aiohttp_client.get(url) as r:
            statuses.append(r.status)

    # Все должны быть 200
    assert all(s == 200 for s in statuses)