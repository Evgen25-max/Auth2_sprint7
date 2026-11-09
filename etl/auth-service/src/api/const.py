
from typing import Final

# Ключи Redis
PERMS_CACHE_PREFIX: Final = 'auth:perms'
BLACKLIST_PREFIX: Final = 'auth:blacklist'
REFRESH_ACTIVE_PREFIX: Final = 'auth:refresh'
REFRESH_SET_PREFIX: Final = 'auth:refresh_set'

# Ключи для сквозной инвалидации и защиты от брутфорса
USER_VER_PREFIX: Final = 'auth:user_ver'
FAILED_ATTEMPTS_PREFIX: Final = 'auth:failed'
LOCKOUT_PREFIX: Final = 'auth:lockout'

# OAuth state 
OAUTH_STATE_PREFIX: Final = 'auth:oauth_state'
OAUTH_STATE_TTL: Final = 600  # секунд

# Названия провайдеров
PROVIDER_YANDEX: Final = 'yandex'
PROVIDER_VK: Final = 'vk'

# Пагинация истории входов
LOGIN_HISTORY_PAGE_SIZE_MAX: Final = 100
LOGIN_HISTORY_DEFAULT_SIZE: Final = 20

# Системные коды прав
PERM_USER_MANAGE: Final = 'user.manage'
PERM_ROLE_MANAGE: Final = 'role.manage'
PERM_FILM_RESTRICTED_VIEW: Final = 'film.restricted.view'
