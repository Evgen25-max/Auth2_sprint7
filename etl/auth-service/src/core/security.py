import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext
import asyncio
from core.config import config

TOKEN_TYPE_ACCESS = 'access'
TOKEN_TYPE_REFRESH = 'refresh'

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

async def hash_password(password: str) -> str:
    """Асинхронно хеширует пароль, вынося bcrypt в отдельный поток."""
    password_with_pepper = f"{password}{config.PASSWORD_PEPPER}"
    sha256_hash = hashlib.sha256(password_with_pepper.encode('utf-8')).hexdigest()

    # Выносим блокирующую операцию bcrypt в поток
    return await asyncio.to_thread(pwd_context.hash, sha256_hash)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Асинхронно проверяет пароль, вынося bcrypt в отдельный поток."""
    password_with_pepper = f"{plain_password}{config.PASSWORD_PEPPER}"
    sha256_hash = hashlib.sha256(password_with_pepper.encode('utf-8')).hexdigest()

    # Выносим блокирующую операцию проверки в поток
    return await asyncio.to_thread(pwd_context.verify, sha256_hash, hashed_password)


def _create_token(
    user_id: str, token_type: str, lifetime: timedelta,
    is_superuser: bool, version: int = 1,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': user_id,
        'jti': str(uuid.uuid4()),
        'type': token_type,
        'is_superuser': is_superuser,
        'ver': version,
        'iat': now,
        'exp': now + lifetime,
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def create_access_token(user_id: str, is_superuser: bool = False, version: int = 1) -> str:
    return _create_token(
        user_id, TOKEN_TYPE_ACCESS,
        timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
        is_superuser, version,
    )


def create_refresh_token(user_id: str, is_superuser: bool = False, version: int = 1) -> str:
    return _create_token(
        user_id, TOKEN_TYPE_REFRESH,
        timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS),
        is_superuser, version,
    )


def decode_token(token: str) -> dict:
    """Валидирует подпись и срок. Бросает jwt.PyJWTError при ошибке."""
    return jwt.decode(
        token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM],
    )