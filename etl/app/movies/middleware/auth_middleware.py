# app/movies/middleware/auth_middleware.py
import logging

import jwt as pyjwt
import redis
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from functools import lru_cache
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
User = get_user_model()


@lru_cache(maxsize=1)
def get_auth_redis_client():
    """
    Клиент к auth-redis, где хранятся:
    - auth:blacklist:{jti}  — отозванные токены
    - auth:user_ver:{sub}   — версия токенов пользователя
    """
    return redis.Redis(
        host=getattr(settings, 'REDIS_AUTH_HOST', 'auth-redis'),
        port=int(getattr(settings, 'REDIS_AUTH_PORT', 6380)),
        password=getattr(settings, 'REDIS_AUTH_PASSW', None),
        db=int(getattr(settings, 'REDIS_AUTH_DB', 1)),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


class AuthMiddleware:
    """
    Middleware проверяет JWT токены от auth-service
    и связывает их с request.user для Django Admin.
    """

    PUBLIC_PREFIXES = ('/api/v1/movies/',)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(p) for p in self.PUBLIC_PREFIXES):
            return self.get_response(request)

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return self.get_response(request)

        token = auth_header[7:]

        with tracer.start_as_current_span("AuthMiddleware.verify_token") as span:
            span.set_attribute("auth.token_type", "access")
            payload = self._verify_token(token)

            if payload is None:
                span.set_attribute("auth.result", "rejected")
                return JsonResponse(
                    {'detail': 'Invalid or expired token'},
                    status=401,
                )

            span.set_attribute("auth.result", "accepted")
            span.set_attribute("auth.user_id", payload.get('sub', ''))

            # Для админки требуются права суперпользователя
            if request.path.startswith('/admin/'):
                if not payload.get('is_superuser'):
                    span.set_attribute("auth.admin_access", "denied")
                    return JsonResponse(
                        {'detail': 'Admin access required'},
                        status=403,
                    )
                span.set_attribute("auth.admin_access", "granted")

            request.auth_user = payload
            request.META['HTTP_X_USER_ID'] = payload.get('sub')

            # === СВЯЗЫВАЕМ С request.user ДЛЯ DJANGO ADMIN ===
            django_user = self._get_or_create_django_user(payload)
            if django_user is not None:
                request.user = django_user
                span.set_attribute("auth.django_user", django_user.username)

        return self.get_response(request)

    def _get_or_create_django_user(self, payload: dict):
        """
        Ищет/создаёт пользователя Django по sub (user_id из auth-service).
        Использует username для хранения UUID.
        """
        user_id = payload.get('sub')
        if not user_id:
            return None

        is_superuser = payload.get('is_superuser', False)

        try:
            user, created = User.objects.get_or_create(
                username=user_id,
                defaults={
                    'is_staff': True,
                    'is_superuser': is_superuser,
                    'is_active': True,
                }
            )

            if created:
                user.set_unusable_password()
                user.save()
                logger.info('Создан Django-пользователь для auth user %s', user_id)

            # Синхронизируем is_superuser, если изменилось
            if user.is_superuser != is_superuser:
                user.is_superuser = is_superuser
                user.is_staff = is_superuser
                user.save(update_fields=['is_superuser', 'is_staff'])
                logger.info('Обновлён is_superuser=%s для %s', is_superuser, user_id)

            return user

        except Exception as e:
            logger.error('Ошибка создания/поиска Django user: %s', e)
            return None

    def _verify_token(self, token: str) -> dict | None:
        secret = getattr(settings, 'JWT_SECRET_KEY', 'change-me')
        algorithm = getattr(settings, 'JWT_ALGORITHM', 'HS256')
        try:
            payload = pyjwt.decode(token, secret, algorithms=[algorithm])
        except pyjwt.ExpiredSignatureError:
            return None
        except pyjwt.PyJWTError:
            return None

        if payload.get('type') != 'access':
            return None

        # Проверка blacklist (logout)
        jti = payload.get('jti')
        if jti and self._is_blacklisted(jti):
            return None

        # Проверка версии токена (смена пароля)
        if self._is_token_version_stale(payload):
            return None

        return payload

    def _is_blacklisted(self, jti: str) -> bool:
        with tracer.start_as_current_span("AuthMiddleware.check_blacklist") as span:
            span.set_attribute("auth.jti", jti)
            try:
                r = get_auth_redis_client()
                result = bool(r.exists(f'auth:blacklist:{jti}'))
                span.set_attribute("auth.blacklisted", result)
                return result
            except Exception as e:
                logger.warning('Redis недоступен при проверке blacklist: %s', e)
                span.set_attribute("auth.redis_available", False)
                return False

    def _is_token_version_stale(self, payload: dict) -> bool:
        """Проверяет, не устарела ли версия токена (после смены пароля)."""
        sub = payload.get('sub')
        token_ver = payload.get('ver', 1)
        if not sub:
            return False

        try:
            r = get_auth_redis_client()
            current_ver_str = r.get(f'auth:user_ver:{sub}')
            if current_ver_str is not None:
                current_ver = int(current_ver_str)
                if int(token_ver) < current_ver:
                    logger.warning(
                        'Token version stale for user %s: token=%s, current=%s',
                        sub, token_ver, current_ver,
                    )
                    return True
        except Exception as e:
            logger.warning('Redis недоступен при проверке user_ver: %s', e)
            return False
        return False