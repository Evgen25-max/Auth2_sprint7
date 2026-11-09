import uuid
from datetime import datetime

from core.config import config
from db.postgres import Base
from sqlalchemy import (Boolean, DateTime, ForeignKey, String, Text, text,
                        UniqueConstraint, func, Integer, Index)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (
        UniqueConstraint('login', name='uq_users_login'),
        {'schema': config.POSTGRES_AUTH_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text('gen_random_uuid()'),
    )
    login: Mapped[str] = mapped_column(String(255), nullable=False)
    # NULL для OAuth-пользователей без пароля
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text('false')
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=text('CURRENT_TIMESTAMP'),
    )
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text('1')
    )

    # Связи
    roles: Mapped[list['Role']] = relationship(
        secondary='auth.user_roles',
        back_populates='users',
        lazy='selectin',
    )
    login_histories: Mapped[list['LoginHistory']] = relationship(
        back_populates='user',
        lazy='select',
    )
    social_accounts: Mapped[list['UserSocialAccount']] = relationship(
        back_populates='user',
        lazy='selectin',
        cascade='all, delete-orphan',
    )


class UserSocialAccount(Base):
    """Привязка внешнего аккаунта соцсети к пользователю."""
    __tablename__ = 'user_social_accounts'
    __table_args__ = (
        UniqueConstraint('provider', 'external_id',
                         name='uq_social_provider_external_id'),
        Index('ix_social_user_provider', 'user_id', 'provider'),
        {'schema': config.POSTGRES_AUTH_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text('gen_random_uuid()'),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('auth.users.id', ondelete='CASCADE',
                   name='fk_social_user_id'),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()')
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()')
    )

    user: Mapped['User'] = relationship(back_populates='social_accounts')


class Role(Base):
    __tablename__ = 'roles'
    __table_args__ = (
        UniqueConstraint('name', name='uq_roles_name'),
        {'schema': config.POSTGRES_AUTH_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text('gen_random_uuid()'),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()')
    )

    users: Mapped[list['User']] = relationship(
        secondary='auth.user_roles',
        back_populates='roles',
        lazy='select',
    )
    permissions: Mapped[list['Permission']] = relationship(
        secondary='auth.role_permissions',
        back_populates='roles',
        lazy='selectin',
    )


class Permission(Base):
    __tablename__ = 'permissions'
    __table_args__ = (
        UniqueConstraint('codename', name='uq_permissions_codename'),
        {'schema': config.POSTGRES_AUTH_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text('gen_random_uuid()'),
    )
    codename: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()')
    )

    roles: Mapped[list['Role']] = relationship(
        secondary='auth.role_permissions',
        back_populates='permissions',
        lazy='select',
    )


class UserRole(Base):
    __tablename__ = 'user_roles'
    __table_args__ = (
        Index('ix_user_roles_role_id', 'role_id'),
        {'schema': config.POSTGRES_AUTH_SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('auth.users.id', ondelete='CASCADE', name='fk_user_roles_user_id'),
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('auth.roles.id', ondelete='CASCADE', name='fk_user_roles_role_id'),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()')
    )


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    __table_args__ = (
        Index('ix_role_permissions_permission_id', 'permission_id'),
        {'schema': config.POSTGRES_AUTH_SCHEMA},
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('auth.roles.id', ondelete='CASCADE',
                   name='fk_role_permissions_role_id'),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('auth.permissions.id', ondelete='CASCADE',
                   name='fk_role_permissions_permission_id'),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()')
    )


class LoginHistory(Base):
    __tablename__ = 'login_history'
    __table_args__ = (
        Index('ix_login_history_user_id', 'user_id'),
        Index('ix_login_history_created_at', 'created_at'),
        {'schema': config.POSTGRES_AUTH_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text('gen_random_uuid()'),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('auth.users.id', ondelete='SET NULL',
                   name='fk_login_history_user_id'),
        nullable=True,
    )
    login: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()')
    )

    user: Mapped['User | None'] = relationship(
        back_populates='login_histories',
        lazy='select',
    )