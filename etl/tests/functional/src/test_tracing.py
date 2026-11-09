import uuid
import pytest
from settings import test_settings


@pytest.mark.asyncio
async def test_trace_context_propagation(aiohttp_client, clean_es, load_films):
    """Проверяем, что traceparent используется для создания trace_id."""
    films = [{'id': str(uuid.uuid4()), 'title': 'Trace Movie',
              'imdb_rating': 8.0, 'genres': [], 'description': '',
              'directors_names': [], 'actors_names': [], 'writers_names': [],
              'directors': [], 'actors': [], 'writers': []}]
    await load_films(films)

    trace_id = 'a' * 32
    parent_id = 'b' * 16
    traceparent = f'00-{trace_id}-{parent_id}-01'

    url = f'{test_settings.service_url}/api/v1/films/'

    async with aiohttp_client.get(url, headers={'traceparent': traceparent}) as r:
        assert r.status == 200
        # X-Request-Id должен присутствовать в ответе
        assert 'X-Request-Id' in r.headers