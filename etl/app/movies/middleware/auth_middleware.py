import json
import logging
import jwt as pyjwt
import redis
from django.conf import settings
from django.http import JsonResponse
from functools import lru_cache
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@lru_cache(maxsize=1)
def get_redis_client():
    return redis.Redis(
        host=getattr(settings, 'REDIS_HOST', 'redis'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        password=getattr(settings, 'REDIS_PASSW', None),
        db=getattr(settings, 'REDIS_AUTH_DB', 1),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


class AuthMiddleware:
    """
    Middleware проверяет JWT токены.
    """

    PROTECTED_PREFIXES = ('/admin/',)
    PUBLIC_PREFIXES = ('/api/v1/movies/',)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Публичные эндпоинты пропускаем всегда
        if any(request.path.startswith(p) for p in self.PUBLIC_PREFIXES):
            return self.get_response(request)

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return self.get_response(request)

        token = auth_header[7:]

        # === КАСТОМНЫЙ СПАН для проверки токена ===
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

            # Для админки требуются права admin или is_superuser
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

        return self.get_response(request)

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

        jti = payload.get('jti')
        if jti and self._is_blacklisted(jti):
            return None

        return payload

    def _is_blacklisted(self, jti: str) -> bool:
        with tracer.start_as_current_span("AuthMiddleware.check_blacklist") as span:
            span.set_attribute("auth.jti", jti)
            try:
                r = get_redis_client()
                result = bool(r.exists(f'auth:blacklist:{jti}'))
                span.set_attribute("auth.blacklisted", result)
                return result
            except Exception as e:
                logger.warning('Redis недоступен при проверке blacklist: %s', e)
                span.set_attribute("auth.redis_available", False)
                return False