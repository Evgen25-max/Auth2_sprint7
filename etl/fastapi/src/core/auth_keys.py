
"""
Единый контракт ключей auth-redis.
"""

from typing import Final

BLACKLIST_PREFIX: Final = 'auth:blacklist'
PERMS_CACHE_PREFIX: Final = 'auth:perms'
USER_VER_PREFIX: Final = 'auth:user_ver'
REFRESH_ACTIVE_PREFIX: Final = 'auth:refresh'