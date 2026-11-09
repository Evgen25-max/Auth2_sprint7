
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from models.auth_models import User
from models.login_history import LoginHistoryItem
from models.users import UserPublic, UserUpdate
from services.auth import AuthService, get_auth_service
from api.deps import get_current_user, require_permission
from api.const import PERM_ROLE_MANAGE, PERM_USER_MANAGE

router = APIRouter(prefix='/users', tags=['Users'])


@router.patch(
    '/me',
    response_model=UserPublic,
    summary='Обновить личный профиль',
)
async def update_profile(
    data: UserUpdate,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    """Изменяет логин, пароль или имя текущего пользователя."""
    return await service.update_profile(
        user_id=user.id,
        current_password=data.current_password,
        login=data.login,
        password=data.password,
        first_name=data.first_name,
        last_name=data.last_name,
    )


@router.get(
    '/{user_id}/permissions',
    summary='Получить права пользователя (для интеграции)',
)
async def get_user_permissions_endpoint(
    user_id: UUID,
    service: AuthService = Depends(get_auth_service),
    _: User = Depends(require_permission(PERM_USER_MANAGE)),
):
    perms = await service.rbac.get_user_permissions(user_id)
    return {'permissions': list(perms)}


@router.get(
    '/me/history',
    response_model=List[LoginHistoryItem],
    summary='История входов',
)
async def get_login_history(
    limit: int = Query(20, ge=1, le=100, description='Количество записей'),
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> List[LoginHistoryItem]:
    """Возвращает последние N попыток входа текущего пользователя."""
    entries = await service.get_login_history(user.id, limit=limit)
    return [LoginHistoryItem.model_validate(e) for e in entries]
