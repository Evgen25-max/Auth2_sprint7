
class UserAlreadyExistsError(Exception):
    """Пользователь с таким логином уже существует."""

    def __init__(self, login: str):
        self.login = login
        super().__init__(f'Пользователь {login} уже зарегистрирован')


class InvalidCredentialsError(Exception):
    """Неверный логин или пароль."""

    def __init__(self):
        super().__init__('Неверный логин или пароль')


class UserNotFoundError(Exception):
    """Пользователь не найден по ID."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f'Пользователь {user_id} не найден')


class TokenError(Exception):
    """Ошибка токена (истек, отозван, неверный тип)."""

    def __init__(self, reason: str = 'invalid token'):
        self.reason = reason
        super().__init__(reason)


class RoleAlreadyExistsError(Exception):
    """Роль с таким именем уже существует."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f'Роль {name} уже существует')


class RoleNotFoundError(Exception):
    """Роль не найдена."""

    def __init__(self, role_id: str):
        self.role_id = role_id
        super().__init__(f'Роль {role_id} не найдена')


class PermissionNotFoundError(Exception):
    """Разрешение не найдено по кодовому имени."""

    def __init__(self, codename: str):
        self.codename = codename
        super().__init__(f'Разрешение {codename} не найдено')