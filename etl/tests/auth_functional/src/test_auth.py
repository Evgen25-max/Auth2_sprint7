import uuid

import pytest

from settings import test_settings

BASE_URL = test_settings.service_url


def bearer(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.asyncio
async def test_signup_success(aiohttp_client, clean_db, clean_redis):
    payload = {
        'login': f'new_user_{uuid.uuid4().hex[:8]}',
        'password': 'StrongPass123!',
        'first_name': 'New',
        'last_name': 'User',
    }

    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json=payload,
    )

    assert response.status == 201, await response.text()

    data = await response.json()

    assert data['login'] == payload['login']
    assert data['first_name'] == payload['first_name']
    assert data['last_name'] == payload['last_name']
    assert data['roles'] == ['user']
    assert 'hashed_password' not in data


@pytest.mark.asyncio
async def test_signup_duplicate_login(aiohttp_client, clean_db, clean_redis):
    payload = {
        'login': f'duplicate_{uuid.uuid4().hex[:8]}',
        'password': 'StrongPass123!',
        'first_name': 'Dup',
        'last_name': 'User',
    }

    first = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json=payload,
    )
    assert first.status == 201, await first.text()

    second = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json=payload,
    )
    assert second.status == 409, await second.text()


@pytest.mark.asyncio
async def test_signup_validation_error(aiohttp_client, clean_db, clean_redis):
    payload = {
        'login': 'ab',
        'password': '123',
        'first_name': '',
        'last_name': '',
    }

    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json=payload,
    )

    assert response.status == 422, await response.text()


@pytest.mark.asyncio
async def test_login_success(aiohttp_client, registered_user):
    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': registered_user['user']['login'],
            'password': registered_user['password'],
        },
    )

    assert response.status == 200, await response.text()

    data = await response.json()

    assert 'access_token' in data
    assert 'refresh_token' in data
    assert data['token_type'] == 'bearer'


@pytest.mark.asyncio
async def test_login_invalid_password(aiohttp_client, registered_user):
    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': registered_user['user']['login'],
            'password': 'WrongPassword123!',
        },
    )

    assert response.status == 401, await response.text()


@pytest.mark.asyncio
async def test_login_unknown_user(aiohttp_client, clean_db, clean_redis):
    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': 'does_not_exist',
            'password': 'Whatever123!',
        },
    )

    assert response.status == 401, await response.text()


# =====================
# Me
# =====================

@pytest.mark.asyncio
async def test_me_without_token(aiohttp_client, clean_db, clean_redis):
    response = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
    )

    assert response.status == 401, await response.text()


@pytest.mark.asyncio
async def test_me_with_invalid_token(aiohttp_client, clean_db, clean_redis):
    response = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers={'Authorization': 'Bearer invalid.token.here'},
    )

    assert response.status == 401, await response.text()


@pytest.mark.asyncio
async def test_me_success(aiohttp_client, registered_user):
    response = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers=bearer(registered_user['access_token']),
    )

    assert response.status == 200, await response.text()

    data = await response.json()

    assert data['id'] == registered_user['user']['id']
    assert data['login'] == registered_user['user']['login']
    assert data['roles'] == ['user']


# =====================
# Refresh
# =====================

@pytest.mark.asyncio
async def test_refresh_returns_new_pair(aiohttp_client, registered_user):
    old_refresh = registered_user['refresh_token']

    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/refresh',
        json={'refresh_token': old_refresh},
    )

    assert response.status == 200, await response.text()

    data = await response.json()

    assert 'access_token' in data
    assert 'refresh_token' in data
    assert data['refresh_token'] != old_refresh


@pytest.mark.asyncio
async def test_refresh_old_refresh_fails_after_rotation(
    aiohttp_client,
    registered_user,
):
    """
    После успешного refresh старый refresh-token должен стать невалидным.
    Это защита от повторного использования украденного refresh-токена.
    """
    old_refresh = registered_user['refresh_token']

    first = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/refresh',
        json={'refresh_token': old_refresh},
    )
    assert first.status == 200, await first.text()

    second = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/refresh',
        json={'refresh_token': old_refresh},
    )
    assert second.status == 401, await second.text()


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(aiohttp_client, registered_user):
    """
    Нельзя использовать access-token вместо refresh-token.
    """
    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/refresh',
        json={'refresh_token': registered_user['access_token']},
    )

    assert response.status == 401, await response.text()


# =====================
# Logout
# =====================

@pytest.mark.asyncio
async def test_logout_revokes_access_token(aiohttp_client, registered_user):
    access_token = registered_user['access_token']

    me_before = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers=bearer(access_token),
    )
    assert me_before.status == 200, await me_before.text()

    logout = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/logout',
        headers=bearer(access_token),
    )
    assert logout.status == 204, await logout.text()

    me_after = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers=bearer(access_token),
    )
    assert me_after.status == 401, await me_after.text()


# =====================
# Roles
# =====================

@pytest.mark.asyncio
async def test_roles_list_requires_role_manage(
    aiohttp_client,
    registered_user,
    admin_token,
):
    """
    Обычный пользователь не должен иметь доступ к списку ролей.
    Админ/superuser — должен.
    """
    forbidden = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(registered_user['access_token']),
    )
    assert forbidden.status == 403, await forbidden.text()

    allowed = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(admin_token),
    )
    assert allowed.status == 200, await allowed.text()

    data = await allowed.json()
    role_names = {role['name'] for role in data}

    assert 'user' in role_names
    assert 'admin' in role_names


@pytest.mark.asyncio
async def test_create_role_requires_role_manage(
    aiohttp_client,
    registered_user,
):
    role_name = f'no_access_role_{uuid.uuid4().hex[:6]}'

    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(registered_user['access_token']),
        json={
            'name': role_name,
            'description': 'Should fail',
            'permissions': [],
        },
    )

    assert response.status == 403, await response.text()


@pytest.mark.asyncio
async def test_create_assign_and_revoke_role(
    aiohttp_client,
    admin_token,
    registered_user,
):
    """
    Проверяем полный цикл:
    1. Админ создает роль с разрешением role.manage
    2. Назначает роль пользователю
    3. Пользователь получает доступ к /roles/
    4. Админ отзывает роль
    5. Пользователь снова получает 403
    """
    user_id = registered_user['user']['id']
    user_token = registered_user['access_token']

    role_name = f'manager_{uuid.uuid4().hex[:6]}'

    create_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(admin_token),
        json={
            'name': role_name,
            'description': 'Role with manage permissions',
            'permissions': ['role.manage'],
        },
    )

    assert create_response.status == 201, await create_response.text()

    created_role = await create_response.json()
    assert created_role['name'] == role_name
    assert 'role.manage' in created_role['permissions']

    assign_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/roles/assign/{user_id}/{role_name}',
        headers=bearer(admin_token),
    )

    assert assign_response.status == 204, await assign_response.text()

    allowed_response = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(user_token),
    )

    assert allowed_response.status == 200, await allowed_response.text()

    revoke_response = await aiohttp_client.delete(
        f'{BASE_URL}/api/v1/roles/revoke/{user_id}/{role_name}',
        headers=bearer(admin_token),
    )

    assert revoke_response.status == 204, await revoke_response.text()

    forbidden_response = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(user_token),
    )

    assert forbidden_response.status == 403, await forbidden_response.text()


@pytest.mark.asyncio
async def test_create_role_with_unknown_permission_fails(
    aiohttp_client,
    admin_token,
):
    role_name = f'bad_perm_role_{uuid.uuid4().hex[:6]}'

    response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(admin_token),
        json={
            'name': role_name,
            'description': 'Role with unknown permission',
            'permissions': ['this.permission.does.not.exist'],
        },
    )

    assert response.status == 404, await response.text()


@pytest.mark.asyncio
async def test_delete_role_invalidates_perms_cache(
    aiohttp_client,
    admin_token,
    registered_user,
):
    """
    Сценарий:
    1. Пользователю назначается роль с правом role.manage
    2. Он делает запрос к защищённому эндпоинту (право кешируется)
    3. Админ удаляет роль
    4. Повторный запрос пользователя возвращает 403
    """
    user_id = registered_user['user']['id']
    user_token = registered_user['access_token']

    role_name = f'manager_{uuid.uuid4().hex[:6]}'
    create = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(admin_token),
        json={'name': role_name, 'description': '', 'permissions': ['role.manage']},
    )
    assert create.status == 201, await create.text()


    created_role = await create.json()
    role_id = created_role['id']

    assign = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/roles/assign/{user_id}/{role_name}',
        headers=bearer(admin_token),
    )
    assert assign.status == 204, await assign.text()

    first = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(user_token),
    )
    assert first.status == 200, await first.text()

    delete = await aiohttp_client.delete(
        f'{BASE_URL}/api/v1/roles/{role_id}',
        headers=bearer(admin_token),
    )
    assert delete.status == 204, await delete.text()

    second = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/roles/',
        headers=bearer(user_token),
    )
    assert second.status == 403, await second.text()


@pytest.mark.asyncio
async def test_change_password_invalidates_tokens(aiohttp_client, registered_user):
    """
    Сценарий:
    1. Пользователь логинится и получает пару токенов
    2. Токены работают корректно
    3. Пользователь меняет пароль
    4. Старый access_token больше не работает (401)
    5. Старый refresh_token больше не работает (401)
    """
    old_access_token = registered_user['access_token']
    old_refresh_token = registered_user['refresh_token']
    old_password = registered_user['password']
    new_password = 'NewStrongPass123!'

    me_before = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers=bearer(old_access_token),
    )
    assert me_before.status == 200, await me_before.text()

    refresh_before = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/refresh',
        json={'refresh_token': old_refresh_token},
    )
    assert refresh_before.status == 200, await refresh_before.text()

    change_password = await aiohttp_client.patch(
        f'{BASE_URL}/api/v1/users/me',
        headers=bearer(old_access_token),
        json={
            'current_password': old_password,
            'password': new_password,
        },
    )
    assert change_password.status == 200, await change_password.text()

    me_after = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers=bearer(old_access_token),
    )
    assert me_after.status == 401, await me_after.text()

    refresh_after = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/refresh',
        json={'refresh_token': old_refresh_token},
    )
    assert refresh_after.status == 401, await refresh_after.text()

    login_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': registered_user['user']['login'],
            'password': new_password,
        },
    )
    assert login_response.status == 200, await login_response.text()

    new_tokens = await login_response.json()
    assert 'access_token' in new_tokens
    assert 'refresh_token' in new_tokens

    me_with_new = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers=bearer(new_tokens['access_token']),
    )
    assert me_with_new.status == 200, await me_with_new.text()


# ==========================================
# Тесты для проверки bcrypt (72 байта)
# ==========================================


@pytest.mark.asyncio
async def test_signup_with_long_password(aiohttp_client, clean_db, clean_redis):
    """
    Интеграционный тест: регистрация пользователя с длинным паролем.
    Проверяет, что API корректно работает с паролями > 72 байт
    благодаря предварительному хешированию SHA-256.
    """
    long_password = "a" * 100
    payload = {
        'login': f'long_pass_user_{uuid.uuid4().hex[:8]}',
        'password': long_password,
        'first_name': 'Test',
        'last_name': 'User',
    }
    signup_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/signup',
        json=payload,
    )
    assert signup_response.status == 201, await signup_response.text()

    login_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': payload['login'],
            'password': long_password,
        },
    )
    assert login_response.status == 200, await login_response.text()

    wrong_login = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': payload['login'],
            'password': "a" * 99 + "b",
        },
    )
    assert wrong_login.status == 401, await wrong_login.text()


@pytest.mark.asyncio
async def test_change_password_to_long_password(aiohttp_client, registered_user):
    """
    Интеграционный тест: смена пароля на длинный пароль.
    Проверяет, что смена пароля работает корректно для паролей > 72 байт.
    """
    old_password = registered_user['password']
    new_long_password = "x" * 150

    change_response = await aiohttp_client.patch(
        f'{BASE_URL}/api/v1/users/me',
        headers=bearer(registered_user['access_token']),
        json={
            'current_password': old_password,
            'password': new_long_password,
        },
    )
    assert change_response.status == 200, await change_response.text()

    login_response = await aiohttp_client.post(
        f'{BASE_URL}/api/v1/auth/login',
        json={
            'login': registered_user['user']['login'],
            'password': new_long_password,
        },
    )
    assert login_response.status == 200, await login_response.text()

    me_after = await aiohttp_client.get(
        f'{BASE_URL}/api/v1/auth/me',
        headers=bearer(registered_user['access_token']),
    )
    assert me_after.status == 401, await me_after.text()
