from fastapi import APIRouter, Depends, Request, status
from models.auth_models import User
from models.token import RefreshRequest, TokenPair
from models.users import UserCreate, UserLogin, UserPublic
from services.auth import AuthService, get_auth_service

from api.deps import get_current_user, get_token_payload

router = APIRouter(prefix='/auth', tags=['Authentication'])


@router.post(
    '/signup',
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary='Регистрация нового пользователя',
)
async def signup(
    data: UserCreate,
    service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    """Создает нового пользователя с базовой ролью 'user'."""
    return await service.signup(data)


@router.post(
    '/login',
    response_model=TokenPair,
    summary='Вход в систему',
)
async def login(
    request: Request,
    data: UserLogin,
    service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    """Выдает пару JWT токенов при успешном логине."""
    ip = request.client.host if request.client else None
    ua = request.headers.get('User-Agent')
    return await service.login(data, ip=ip, ua=ua)


@router.post(
    '/refresh',
    response_model=TokenPair,
    summary='Обновление access-токена',
)
async def refresh_tokens(
    body: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    """Выдает новую пару токенов по refresh-токену."""
    return await service.refresh(body.refresh_token)


@router.post(
    '/logout',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Выход из системы',
)
async def logout(
    payload: dict = Depends(get_token_payload),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Отзывает текущий access-токен и активный refresh-токен."""
    await service.logout(payload)


@router.get(
    '/me',
    response_model=UserPublic,
    summary='Текущий пользователь',
)
async def get_me(
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    """Возвращает данные текущего авторизованного пользователя."""
    return await service.get_me(user.id)
