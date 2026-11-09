
class UserAlreadyExistsError(Exception):
    def __init__(self, login: str):
        self.login = login
        super().__init__(f'Пользователь {login} уже зарегистрирован')


class InvalidCredentialsError(Exception):
    def __init__(self):
        super().__init__('Неверный логин или пароль')


class UserNotFoundError(Exception):
    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f'Пользователь {user_id} не найден')


class TokenError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)


class RoleAlreadyExistsError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f'Роль {name} уже существует')


class RoleNotFoundError(Exception):
    def __init__(self, role_id: str):
        self.role_id = role_id
        super().__init__(f'Роль {role_id} не найдена')


class PermissionNotFoundError(Exception):
    def __init__(self, codename: str):
        self.codename = codename
        super().__init__(f'Разрешение {codename} не найдено')


class AccountLockedError(Exception):
    def __init__(self, login: str):
        self.login = login
        super().__init__(f'Аккаунт {login} временно заблокирован')


# === OAuth / Social ===

class OAuthProviderError(Exception):
    """Ошибка при обмене с OAuth-провайдером."""
    def __init__(self, detail: str = 'OAuth provider error'):
        self.detail = detail
        super().__init__(detail)


class OAuthStateError(Exception):
    """Некорректный, истёкший или использованный state."""
    def __init__(self):
        super().__init__('Некорректный или истёкший параметр state')


class SocialAccountAlreadyLinkedError(Exception):
    """Соцсеть уже привязана к этому пользователю."""
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f'Аккаунт {provider} уже привязан к вашему профилю')


class SocialAccountLinkedToAnotherUserError(Exception):
    """Соцсеть уже привязана к другому пользователю."""
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f'Аккаунт {provider} уже привязан к другому пользователю. '
            f'Выполните объединение аккаунтов через /social/merge.'
        )


class SocialAccountNotLinkedError(Exception):
    """Соцсеть не привязана."""
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f'Аккаунт {provider} не привязан')


class CannotUnlinkLastAuthMethodError(Exception):
    """Нельзя открепить единственный способ входа."""
    def __init__(self):
        super().__init__(
            'Нельзя открепить единственный способ входа. '
            'Сначала задайте пароль или привяжите другую соцсеть.'
        )


class MergeRequiresPasswordError(Exception):
    """Для объединения нужен пароль присоединяемого аккаунта."""
    def __init__(self):
        super().__init__(
            'Присоединяемый аккаунт защищён паролем. '
            'Передайте поле merge_password.'
        )


class MergeWithSelfError(Exception):
    """Нельзя объединить аккаунт с самим собой."""
    def __init__(self):
        super().__init__('Нельзя объединить аккаунт с самим собой')