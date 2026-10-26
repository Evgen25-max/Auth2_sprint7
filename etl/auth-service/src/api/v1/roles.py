
from typing import List
from uuid import UUID
from api.const import PERM_ROLE_MANAGE
from fastapi import APIRouter, Depends, status
from models.auth_models import Role, User
from models.role import RoleCreate, RolePublic
from services.rbac import RBACService, get_rbac_service

from api.const import PERM_ROLE_MANAGE
from api.deps import require_permission

router = APIRouter(prefix='/roles', tags=['Roles & Permissions'])


@router.get(
    '/',
    response_model=List[RolePublic],
    summary='Список всех ролей',
)
async def list_roles(
    _: User = Depends(require_permission(PERM_ROLE_MANAGE)),
    service: RBACService = Depends(get_rbac_service),
) -> List[RolePublic]:
    """Возвращает список всех существующих ролей с их правами."""
    roles = await service.list_roles()
    return [RolePublic.model_validate(r) for r in roles]


@router.post('/', response_model=RolePublic, status_code=status.HTTP_201_CREATED)
async def create_new_role(
    body: RoleCreate,
    service: RBACService = Depends(get_rbac_service),
    _: User = Depends(require_permission(PERM_ROLE_MANAGE)),
):
    role = await service.create_role(
        name=body.name,
        description=body.description,
        permission_codenames=body.permissions
    )
    return role


@router.delete(
    '/{role_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить роль',
)
async def delete_role(
    role_id: UUID,
    _: User = Depends(require_permission(PERM_ROLE_MANAGE)),
    service: RBACService = Depends(get_rbac_service),
) -> None:
    """Удаляет роль."""
    await service.delete_role(role_id)


@router.post(
    '/assign/{user_id}/{role_name}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Назначить роль пользователю',
)
async def assign_role(
    user_id: UUID,
    role_name: str,
    _: User = Depends(require_permission(PERM_ROLE_MANAGE)),
    service: RBACService = Depends(get_rbac_service),
) -> None:
    """Добавляет указанную роль пользователю."""
    await service.assign_role_to_user(user_id, role_name)


@router.delete(
    '/revoke/{user_id}/{role_name}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Отобрать роль у пользователя',
)
async def revoke_role(
    user_id: UUID,
    role_name: str,
    _: User = Depends(require_permission(PERM_ROLE_MANAGE)),
    service: RBACService = Depends(get_rbac_service),
) -> None:
    """Убирает указанную роль у пользователя."""
    await service.remove_role_from_user(user_id, role_name)
