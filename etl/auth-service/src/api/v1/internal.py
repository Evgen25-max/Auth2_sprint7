"""
Внутренние эндпоинты для service-to-service коммуникации.
Защищены служебным ключом X-Internal-Key.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from core.config import config
from services.rbac import RBACService, get_rbac_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/internal', tags=['Internal API'])


async def verify_internal_key(
    x_internal_key: str = Header(None, alias='X-Internal-Key'),
) -> None:
    """Проверяет служебный ключ для внутренних запросов."""
    if not x_internal_key or x_internal_key != config.INTERNAL_API_KEY:
        logger.warning(
            'Попытка доступа к internal API без валидного ключа',
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Invalid or missing internal API key',
        )


@router.get(
    '/users/{user_id}/permissions',
    summary='Служебный эндпоинт: получить права пользователя',
    dependencies=[Depends(verify_internal_key)],
)
async def get_user_permissions_internal(
    user_id: UUID,
    rbac_service: RBACService = Depends(get_rbac_service),
) -> dict:
    """
    Возвращает права пользователя для внутренних сервисов.
    Требует заголовок X-Internal-Key с валидным ключом.
    """
    permissions = await rbac_service.get_user_permissions(user_id)
    return {'permissions': list(permissions)}