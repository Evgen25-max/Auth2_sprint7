from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestSettings(BaseSettings):
    """Настройки функциональных тестов auth-service."""

    service_url: str = Field(
        default='http://127.0.0.1:8001',
        alias='SERVICE_URL',
    )


    postgres_host: str = Field(
        default='127.0.0.1',
        alias='TEST_POSTGRES_HOST',
    )
    postgres_port: int = Field(
        default=5432,
        alias='TEST_POSTGRES_PORT',
    )
    postgres_user: str = Field(
        default='auth_admin',
        alias='TEST_POSTGRES_USER',
    )
    postgres_password: str = Field(
        default='secret',
        alias='TEST_POSTGRES_PASSWORD',
    )
    postgres_db: str = Field(
        default='auth_service_db',
        alias='TEST_POSTGRES_DB',
    )
    auth_schema: str = Field(
        default='auth',
        alias='TEST_AUTH_SCHEMA',
    )


    redis_host: str = Field(
        default='127.0.0.1',
        alias='TEST_REDIS_HOST',
    )
    redis_port: int = Field(
        default=6379,
        alias='TEST_REDIS_PORT',
    )
    redis_password: str | None = Field(
        default=None,
        alias='TEST_REDIS_PASSW',
    )
    redis_db: int = Field(
        default=1,
        alias='TEST_REDIS_DB',
    )

    password_pepper: str = Field(
        default='test-password-pepper',
        alias='PASSWORD_PEPPER',
    )

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_ignore_empty=True,
        extra='ignore',
    )


test_settings = TestSettings()
