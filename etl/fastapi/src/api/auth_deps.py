
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from core.auth_integration import AuthClient, TokenVerifier, get_auth_client
from db.auth_redis import get_auth_redis

bearer_scheme = HTTPBearer(auto_error=False)


async def get_token_verifier(
    request: Request,
    auth_redis: Optional[Redis] = Depends(get_auth_redis),
) -> TokenVerifier:
    auth_client: Optional[AuthClient] = getattr(request.app.state, 'auth_client', None)
    return TokenVerifier(auth_redis=auth_redis, auth_client=auth_client)


async def get_optional_user_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> Optional[dict]:
    """Не падает, если токен отсутствует — просто возвращает None."""
    if credentials is None:
        return None
    return await verifier.verify_token(credentials.credentials)


async def require_auth(
    payload: Optional[dict] = Depends(get_optional_user_payload),
) -> dict:
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется аутентификация',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return payload


def require_permission(perm_codename: str):
    """Фабрика зависимостей для проверки прав."""
    async def checker(
        payload: dict = Depends(require_auth),
        verifier: TokenVerifier = Depends(get_token_verifier),
    ) -> dict:
        # Superuser обходит проверку прав.
        if payload.get('is_superuser'):
            return payload

        user_id = UUID(payload['sub'])
        perms = await verifier.get_user_permissions(user_id)

        if perm_codename not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Недостаточно прав: требуется {perm_codename}',
            )
        return payload
    return checker