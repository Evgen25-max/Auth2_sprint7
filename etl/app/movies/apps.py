import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MoviesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'movies'

    def ready(self):
        # Всё внутри try: и импорт, и патчинг.
        try:
            import psycopg2  # noqa: F401  — гарантируем импорт ДО патчинга
            from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

            Psycopg2Instrumentor().instrument()
            logger.info('psycopg2 instrumented for OpenTelemetry')
        except Exception as exc:
            logger.warning('psycopg2 instrument skipped: %s', exc)