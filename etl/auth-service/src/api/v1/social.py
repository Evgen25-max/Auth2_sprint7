
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.deps import get_current_user, get_optional_user
from core.http import trusted_client_ip
from models.auth_models import User
from models.social import (
    AuthorizeResponse,
    MergeAccountsRequest,
    SocialAccountPublic,
    SocialLoginRequest,
)
from models.token import TokenPair
from models.users import UserPublic
from services.social import SocialAuthService, get_social_service

router = APIRouter(prefix='/social', tags=['Social Auth'])


@router.get(
    '/linked',
    response_model=list[SocialAccountPublic],
    summary='Список привязанных соцсетей текущего пользователя',
)
async def list_linked_accounts(
    user: User = Depends(get_current_user),
    service: SocialAuthService = Depends(get_social_service),
) -> list[SocialAccountPublic]:
    return await service.get_linked_accounts(user.id)


@router.post(
    '/merge',
    response_model=UserPublic,
    summary='Ручное объединение аккаунтов в ЛК',
)
async def merge_accounts(
    body: MergeAccountsRequest,
    user: User = Depends(get_current_user),
    service: SocialAuthService = Depends(get_social_service),
) -> UserPublic:
    """
    Присоединяет аккаунт, найденный по соцсети, к текущему аккаунту.

    Если присоединяемый аккаунт защищён паролем — необходимо передать
    поле `merge_password`.
    """
    return await service.merge_accounts(
        user_id=user.id,
        provider_name=body.provider,
        code=body.code,
        state=body.state,
        merge_password=body.merge_password,
    )


@router.get(
    '/{provider}/authorize',
    response_model=AuthorizeResponse,
    summary='Получить ссылку на авторизацию в соцсети',
)
async def authorize(
    provider: str,
    purpose: str = Query('login', pattern='^(login|link|merge)$'),
    redirect_uri: str | None = None,
    user: User | None = Depends(get_optional_user),
    service: SocialAuthService = Depends(get_social_service),
) -> AuthorizeResponse:
    """
    Возвращает ссылку на страницу авторизации провайдера и одноразовый `state`.

    - purpose=login — публичный вход/регистрация;
    - purpose=link  — привязка соцсети к текущему аккаунту (нужен токен);
    - purpose=merge — подготовка к объединению аккаунтов (нужен токен).
    """
    if purpose in ('link', 'merge') and user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется авторизация',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    user_id = user.id if user else None
    result = await service.get_authorize_url(
        provider_name=provider,
        purpose=purpose,
        user_id=user_id,
        redirect_uri=redirect_uri,
    )
    return AuthorizeResponse(**result)


@router.post(
    '/{provider}/login',
    response_model=TokenPair,
    summary='Вход/регистрация через соцсеть',
)
async def social_login(
    provider: str,
    body: SocialLoginRequest,
    request: Request,
    service: SocialAuthService = Depends(get_social_service),
) -> TokenPair:
    ip = trusted_client_ip(request)
    ua = request.headers.get('User-Agent')
    return await service.oauth_login(
        provider_name=provider,
        code=body.code,
        state=body.state,
        ip=ip,
        ua=ua,
    )


@router.post(
    '/{provider}/link',
    response_model=SocialAccountPublic,
    status_code=status.HTTP_201_CREATED,
    summary='Привязать соцсеть к текущему аккаунту',
)
async def link_social(
    provider: str,
    body: SocialLoginRequest,
    user: User = Depends(get_current_user),
    service: SocialAuthService = Depends(get_social_service),
) -> SocialAccountPublic:
    return await service.link_social(
        user_id=user.id,
        provider_name=provider,
        code=body.code,
        state=body.state,
    )


@router.delete(
    '/{provider}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Открепить соцсеть от личного кабинета',
)
async def unlink_social(
    provider: str,
    user: User = Depends(get_current_user),
    service: SocialAuthService = Depends(get_social_service),
) -> None:
    """
    Открепляет соцсеть от личного кабинета.

    Если это единственный способ входа (нет пароля и других соцсетей),
    операция будет отклонена с ошибкой.
    """
    await service.unlink_social(user.id, provider)